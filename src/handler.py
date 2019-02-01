import socket
import errno
import re
import logging
from collections import deque
from functools import partial
from .gen import Future, coroutine
from .utils import errno_from_exception, \
    merge_prefix, tobytes
from .ioloop import IOLoop, Timer
from .import errors,utils


class BaseHandler:

    def __init__(self, loop: IOLoop):
        self._sock = None
        self._loop = loop

    def handle(self, sock, fd, events):
        raise NotImplementedError(
            "%s not implement method handle!" % self.__class__.__name__
        )

    def close(self):
        self._loop.unregister(self._sock)
        self._sock.close()
        
    def register(self, events=None, cb=None):
        if events is None:
            events = self._loop.READ | self._loop.ERROR
        else:
            events = self._loop.READ | self._loop.ERROR | events
        if not cb:
            cb = self.handle
        self._loop.register(self._sock, events, cb)


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
        self._sock = self.create_sock(**sockopt)
        self.register()

    def create_sock(self, **sockopt):
        addrs = self.getaddrinfo()
        af, socktype, proto, canonname, sa = addrs[0]

        sock = socket.socket(af, socktype, proto)
        sock = self.set_socketopt(sock, **sockopt)
        sock.bind(tuple(sa))
        sock.setblocking(False)
        return sock

    def getaddrinfo(self):
        raise NotImplementedError("duty of subclass")

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

    def getaddrinfo(self):
        addrs = socket.getaddrinfo(
            self._addr[0], self._addr[1], 
            type=socket.SOCK_DGRAM, proto=socket.SOL_UDP)
        if not addrs:
            raise Exception("can't get addrinfo for %s:%d" % self._addr)
        return addrs

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
            logging.warn("UDP: accept error: ", exc)

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

    def close(self):
        super().close()
        self._closed = True
        self._wbuf, self._rbuf = deque(), deque()

    @property
    def events(self):
        e = self._loop.READ
        if self._wbsize:
            e |= self._loop.WRITE
        return e

    def on_read(self, future):
        try:
            data = self._sock.recv(65535)
            future.set_result(data)
        except (OSError, IOError) as exc:
            if errno_from_exception(exc) in (
                errno.ETIMEDOUT, errno.EAGAIN, errno.EWOULDBLOCK):
                return
            else:
                future.set_result(b'')

    def on_write(self, future):
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
        future.set_result(bytes_num)

    def handle_events(self, sock, fd, events, future):
        if events & self._loop.ERROR:
            logging.warn("TCP: socket %s:%d error" % self._addr)
            self.close()
            return
        if events & self._loop.READ:
            self.on_read(future)
        if events & self._loop.WRITE:
            self.on_write(future)

    @coroutine
    def read_forever(self, timeout: int=0):
        f = Future()
        cb = partial(self.handle_events, future=f)
        self._loop.register(self._sock, self.events, cb)
        timer = None
        if timeout:
            timer = self._loop.add_calllater(
                timeout, 
                lambda f: f.cancel(errors.TimeoutError, None, None))
        chunk = yield f
        if timer:
            self._loop.remove_timer(timer)
        if not chunk:
            raise errors.ConnectionClosed(self._addr)
        return chunk

    def _read_nbytes_from_buf(self, n: int) -> bytes:
        assert self._rbsize >= n
        merge_prefix(self._rbuf, n)
        s = self._rbuf.popleft()
        self._rbsize -= n
        return s

    @coroutine
    def read_nbytes(self, n:int, timeout: int=0) -> bytes:

        f = Future()

        if n <= self._rbsize:
            self._loop.add_callsoon(lambda v: v.set_result(None), f)
            yield f
            return self._read_nbytes_from_buf(n)
        
        def on_timeout():
            self.close()
            f.cancel((errors.TimeoutError, None, None))

        timer = None
        if timeout:
            timer = self._loop.add_calllater(timeout, on_timeout)

        cb = partial(self.handle_events, future=f)
        while True:
            self._loop.register(self._sock, self.events, cb)
            chunk = yield f
            if chunk:
                self._rbuf.append(chunk)
                self._rbsize += len(chunk)
                if self._rbsize >= n:
                    if timer:
                        self._loop.remove_timer(timer)
                    return self._read_nbytes_from_buf(n)
            else:
                self.close()
                if timer:
                    self._loop.remove_timer(timer)
                raise errors.ConnectionClosed(self._addr)
            f.clear()

    @coroutine
    def read_until(self, regex: str, maxrange: int=None):
        maxrange = maxrange or 65535
        patt = re.compile(tobytes(regex))
        f = Future(reuse=True)
        while True:
            cb = partial(self.handle_events, future=f)
            self._loop.register(self._sock, self.events, cb)
            chunk = yield f
            if chunk:
                self._rbuf.append(chunk)
                self._rbsize += len(chunk)
                merge_prefix(self._rbuf, maxrange)
                m = patt.search(self._rbuf[0])
                if m:
                    endpos = m.end()
                    merge_prefix(self._rbuf, endpos)
                    data = self._rbuf.popleft()
                    self._rbsize -= endpos
                    return data
                else:
                    if len(self._rbuf[0]) >= maxrange:
                        raise errors.ConnectionClosed(
                            ("[::]", 0), "Entity Too Large")
            else:
                self.close()
                raise errors.ConnectionClosed(self._addr)

    @coroutine
    def write(self, data):
        self._wbuf.append(data)
        self._wbsize += len(data)
        f = Future(True)
        n = 0
        while self._wbsize:
            cb = partial(self.handle_events, future=f)
            self._loop.register(self._sock, self.events, cb)
            num = yield f
            n += num
        self._loop.unregister(self._sock)
        return n


class TCPServer(_ServerHandler):

    def __init__(self, ip, port, 
            backlog=128, loop=None, 
            conn_cls=Connection, **sockopt):
        super().__init__(ip, port, backlog, loop, **sockopt)
        self._sock.listen(self.backlog)
        self.conn_class = conn_cls

    def getaddrinfo(self):
        addrs = socket.getaddrinfo(
            self._addr[0], self._addr[1], 
            type=socket.SOCK_STREAM, proto=socket.SOL_TCP)
        if not addrs:
            raise Exception("can't get addrinfo for %s:%d" % self._addr)
        return addrs

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
            logging.warn("TCP: accept error: ", exc)

    @coroutine
    def handle_conn(self, conn, addr):
        raise NotImplementedError("duty of subclass")


class TCPClient(Connection):

    def __init__(self, **sockopt):
        loop = IOLoop.current()
        self._connected = False
        super().__init__(None, None, loop)

    def on_connected(self, future: Future):
        self._connected = True
        future.set_result(None)

    @coroutine
    def connect(self, addr):
        family = utils.ip_type(addr[0])
        if not family:
            raise ValueError("hostname not support!")
        self._sock = socket.socket(family, socket.SOCK_STREAM)
        self._sock.setblocking(False)
        self._addr = (utils.tostr(addr[0]), addr[1])
        future = Future()
        try:
            self._sock.connect(self._addr)
        except BlockingIOError:
            pass
        cb = partial(self.handle_events, future=future)
        self._loop.register(self._sock, self._loop.WRITE, cb)
        yield future
        self._loop.unregister(self._sock)

    def handle_events(self, sock, fd, events, future):
        if events & self._loop.ERROR:
            logging.warn("TCP: socket %s:%d error" % self._addr)
            self.close()
            return
        if events & self._loop.WRITE:
            if not self._connected:
                self.on_connected(future)
            else:
                self.on_write(future)
        if events & self._loop.READ:
            self.on_read(future)


class UDPClient(BaseHandler):
    
    def __init__(self, sock, addr, loop=None):
        if not loop:
            loop = IOLoop.current()
        super().__init__(loop)
        self._sock = sock
        self._addr = addr
        self._future = None
        self._loop.register(self._sock, self._loop.READ, self.handle)

    def handle(self, sock, fd, events):
        if events & self._loop.READ:
            data, server = self._sock.recvfrom(65535)
            self.on_read(data, server)
        if events & self._loop.ERROR:
            self.close()
            logging.warn("UDP: socket %s:%d error" % self._addr)
            self._future.cancel()

    def on_read(self, data, svr):
        self._future.set_result((data, svr))

    def write(self, req, server):
        self._sock.sendto(req, server)

    def read(self, timeout: int=0):
        self._future = Future()
        def on_timeout():
            self.close()
            self._future.cancel((errors.TimeoutError, None, None))
        if timeout:
            self._loop.add_calllater(timeout, on_timeout)
        return self._future
