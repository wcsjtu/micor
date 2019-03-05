import socket
import errno
import re
import select
import logging
import time
import struct
from collections import deque
from functools import partial
from .gen import Future, coroutine
from .utils import errno_from_exception, \
    merge_prefix, tobytes
from .ioloop import IOLoop, Timer
from .import errors,utils
from .resolvers.poll import resolver


class BaseHandler:

    def __init__(self, loop: IOLoop):
        self._sock = None
        self._loop = loop
        self._rfut = None
        self._wfut = None

    def handle(self, sock, fd, events):
        raise NotImplementedError(
            "%s not implement method handle!" % self.__class__.__name__
        )

    def close(self):
        self._loop.unregister(self._sock)
        self._sock.close()
        
    def register(self, events=None, cb=None):
        if self._sock._closed:
            return
        if events is None:
            events = self._loop.READ | self._loop.ERROR
        else:
            events = self._loop.READ | self._loop.ERROR | events
        if not cb:
            cb = self.handle
        self._loop.register(self._sock, events, cb)

    @coroutine
    def getaddrinfo(self, 
                    host: str, 
                    port: int, 
                    family: int=0, 
                    type: int=0, 
                    proto: int=0, 
                    flags: int=0,
                    timeout: int=0):
        res = yield resolver.getaddrinfo(host, port, family, type, proto, flags, timeout)
        return res


class _ServerHandler(BaseHandler):

    def __init__(self, 
            ip: str,
            port: int,
            backlog: int=128,
            loop: IOLoop=None,
            **sockopt):
        if not loop:
            loop = IOLoop.current()
        super().__init__(loop)
        self._addr = (ip, port)
        self.backlog = backlog
        
    def create_sock(self, ip, port, socktype, proto, **sockopt):
        family = utils.ip_type(ip)
        if not family:
            raise ValueError("invalid ip address %s" % ip)
        
        sock = socket.socket(family, socktype, proto)
        sock = self.set_socketopt(sock, **sockopt)
        sock.bind((ip, port))
        sock.setblocking(False)
        return sock

    def set_socketopt(self, sock, **opt):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock


class Datagram(BaseHandler):

    def __init__(self, sock, addr, data, loop):
        super().__init__(loop)
        self._sock = sock
        self._addr = addr
        self._rbuf = [data]

    def read_package(self):
        return self._rbuf[0]

    def write_package(self, pkg):
        self._sock.sendto(pkg, self._addr)

    def close(self):
        self._rbuf = []
        self._addr = tuple()


class UDPServer(_ServerHandler):

    def __init__(self, ip, port, conn_cls=Datagram,  loop=None, **sockopt):
        super().__init__(ip, port, None, loop, **sockopt)
        self.conn_cls = conn_cls
        self._sock = self.create_sock(
            ip, port, socket.SOCK_DGRAM, socket.SOL_UDP, **sockopt
            )
        self.register()

    def handle(self, sock, fd, events):
        if events & self._loop.ERROR:
            self.close()
            raise Exception('server_socket error')
        try:
            data, addr = self._sock.recvfrom(65535)
            logging.debug("UDP: accept %s:%d" % addr)
            h = self.conn_cls(sock, addr, data, self._loop)
            future = self.handle_datagram(h, addr)

            self._loop.add_future(future, lambda f: f.print_excinfo())
        except (OSError, IOError) as exc:
            logging.warn("UDP: accept error: %s" % exc)

    @coroutine
    def handle_datagram(self, datagram, addr):
        raise NotImplementedError("duty of subclass")


class Connection(BaseHandler):

    def __init__(self, sock, addr, loop):
        super().__init__(loop)
        self._sock = sock
        self._addr = addr
        self._wbuf = deque()
        self._wbsize = 0
        self._rbuf = deque()
        self._rbsize = 0
        self._closed = False
        if self._sock:
            self.register(self.events)

    def close(self):
        if self._closed:
            return
        super().close()
        self._closed = True
        self._wbuf, self._rbuf = deque(), deque()
        self._wbsize, self._rbsize = 0, 0

    @property
    def events(self):
        e = self._loop.READ
        if self._wbsize:
            e |= self._loop.WRITE
        if utils.has_ET:
            e |= select.EPOLLET
        return e

    def on_read(self):
        data = b''
        try:
            data = self._sock.recv(65535)
        except (OSError, IOError) as exc:
            if errno_from_exception(exc) in (
                errno.ETIMEDOUT, errno.EAGAIN, errno.EWOULDBLOCK):
                return
        if self._rfut:
            fut = self._rfut
            self._rfut = None
            fut.set_result(data)
        else:
            if not data:
                self.close()
            # self._rbuf.append(data)
            # self._rbsize += len(data)

    def on_write(self):
        bytes_num = 0
        merge_prefix(self._wbuf, 65535)
        while self._wbsize:
            try:
                num = self._sock.send(self._wbuf[0])
                if num:
                    merge_prefix(self._wbuf, num)
                    self._wbuf.popleft()
                    bytes_num += num
                    self._wbsize -= num
                else:
                    break
            except (socket.error, IOError, OSError) as exc:
                eno = errno_from_exception(exc)
                if eno in (errno.EAGAIN, errno.EINPROGRESS, errno.EWOULDBLOCK):     # 缓冲区满
                    break
                else:
                    self.close()
                    logging.warn("TCP: Write error on %d: %s" % (self._sock.fileno(), exc))
                    break
        if self._wfut and not self._wbsize:
            fut = self._wfut
            self._wfut = None
            fut.set_result(bytes_num)

    def on_error(self):
        logging.warn("TCP: socket %s:%d error" % self._addr)
        if self._wfut:
            self._wfut.cancel((socket.error, None, None))
        if self._rfut:
            self._rfut.cancel((socket.error, None, None))
        self.close()

    def handle(self, sock, fd, events):
        if events & self._loop.ERROR:
            self.on_error()
            return
        if events & self._loop.READ:
            self.on_read()
        if events & self._loop.WRITE:
            self.on_write()
        if not self._closed:
            self.register(self.events)

    def _pop_from_rbuf(self, size):
        merge_prefix(self._rbuf, size)
        res = self._rbuf.popleft()
        self._rbsize -= len(res)
        return res

    @coroutine
    def read_forever(self, timeout: int=0):
        if self._rbsize > 0:
            chunk = yield self.read_from_buf(self._rbsize)
            return chunk
        future = self.read_from_fd()
        timer = None
        if timeout:
            timer = self._loop.add_calllater(timeout,
                    lambda: future.cancel((errors.TimeoutError, None, None))
                )
        chunk = yield future
        if timer:
            self._loop.remove_timer(timer)
        if not chunk:
            self.close()
            raise errors.ConnectionClosed(self._addr)
        return chunk

    def read_from_fd(self):
        future = Future()
        self._rfut = future
        return future

    def read_from_buf(self, n):
        assert self._rbsize >= n
        future = Future()
        res = self._pop_from_rbuf(n)
        self._loop.add_callsoon(lambda v: v.set_result(res), future)
        return future
    
    @coroutine
    def read_nbytes(self, n:int, timeout: int=0) -> bytes:
        if n <= self._rbsize:
            res = yield self.read_from_buf(n)
            return res

        def on_timeout():
            self.close()
            self._rfut.cancel((errors.TimeoutError, None, None))

        timer = None
        if timeout:
            timer = self._loop.add_calllater(timeout, on_timeout)

        while True:
            chunk = yield self.read_from_fd()
            if chunk:
                self._rbuf.append(chunk)
                self._rbsize += len(chunk)
                if self._rbsize >= n:
                    if timer:
                        self._loop.remove_timer(timer)
                    return self._pop_from_rbuf(n)
            else:
                self.close()
                if timer:
                    self._loop.remove_timer(timer)
                raise errors.ConnectionClosed(self._addr)
            

    def write(self, data):
        self._wbuf.append(data)
        self._wbsize += len(data)
        self.register(self.events)
        f = Future()
        self._wfut = f
        return f


class TCPServer(_ServerHandler):

    def __init__(self, ip, port, 
            backlog=128, loop=None, 
            conn_cls=Connection, **sockopt):
        super().__init__(ip, port, backlog, loop, **sockopt)
        self._sock = self.create_sock(
            ip, port, socket.SOCK_STREAM, socket.SOL_TCP, **sockopt
            )
        self._sock.listen(self.backlog)
        self.register()
        self.conn_class = conn_cls

    def handle(self, sock, fd, events):
        if events & self._loop.ERROR:
            self.close()
            raise Exception('server_socket error')
        try:
            conn, addr = self._sock.accept()
            logging.debug("TCP: accept %s:%d" % addr)
            h = self.conn_class(conn, addr, loop = self._loop)
            future = self.handle_conn(h, addr)
            self._loop.add_future(future, lambda f: f.print_excinfo())

        except (OSError, IOError) as exc:
            logging.warn("TCP: accept error: %s" % exc)

    @coroutine
    def handle_conn(self, conn, addr):
        raise NotImplementedError("duty of subclass")


class TCPClient(Connection):

    def __init__(self, **sockopt):
        loop = IOLoop.current()
        self._connected = False
        super().__init__(None, None, loop)
        self._connect_timer = None

    def on_connected(self):
        self._connected = True
        self._wfut.set_result(None)
    
    def _inline_connect(self, family, type, proto, addr, timeout):
        self._sock = socket.socket(family, type, proto)
        self._sock.setblocking(False)
        self._addr = addr
        future = Future()

        self._connect_timer = self._loop.add_calllater(timeout, lambda: future.cancel(
            (errors.TimeoutError, None, None)
        ))

        self._wfut = future
        self.register(self._loop.WRITE)
        try:
            self._sock.connect(self._addr)
        except BlockingIOError:
            pass
        return future

    @coroutine
    def connect(self, addr, timeout=30):
        start = time.time()
        sa = yield self.getaddrinfo(*addr, type=socket.SOCK_STREAM, timeout=timeout)
        timeout -= (time.time() - start)
        for family, type, proto, cn, addr in sa:
            now = time.time()
            if timeout <= 0:
                raise errors.TimeoutError()
            try:
                yield self._inline_connect(family, type, proto, addr, timeout)
                break
            except errors.TimeoutError:
                timeout -= (time.time() - now)
        self._connect_timer.cancel()
        self._connect_timer = None

    def handle_events(self, sock, fd, events):
        if events & self._loop.ERROR:
            self.on_error()
            return
        if events & self._loop.WRITE:
            if not self._connected:
                self.on_connected()
            else:
                self.on_write()
        if events & self._loop.READ:
            self.on_read()
        self.register(self.events)


class UDPClient(BaseHandler):
    
    def __init__(self, sock, addr, loop=None):
        if not loop:
            loop = IOLoop.current()
        super().__init__(loop)
        self._sock = sock
        self._addr = addr
        self._rbuf = list()
        self._loop.register(self._sock, self._loop.READ, self.handle)

    def handle(self, sock, fd, events):
        if events & self._loop.READ:
            data, server = self._sock.recvfrom(65535)
            self.on_read(data, server)
        if events & self._loop.ERROR:
            self.close()
            logging.warn("UDP: socket %s:%d error" % self._addr)
            self._rfut.cancel((socket.error, None, None))

    def on_read(self, data, svr):
        if self._rfut:
            self._rfut.set_result((data, svr))
        else:
            self._rbuf.append((data, svr))

    def write(self, req, server):
        self._sock.sendto(req, server)

    @coroutine
    def read(self, timeout=0):
        if self._rbuf:
            future = Future()
            res = self._rbuf.pop(0)
            self._loop.add_callsoon(lambda: future.set_result(res))
            yield future
            return res
        timer = None
        def on_timeout():
            self.close()
            self._rfut.cancel((errors.TimeoutError, None, None))
        if timeout:
            timer = self._loop.add_calllater(timeout, on_timeout)
        res = yield self._read()
        if timer:
            self._loop.remove_timer(timer)
        return res

    def _read(self):
        self._rfut = Future()
        return self._rfut