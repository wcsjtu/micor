import socket
import errno
import re
import select
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
        if self._sock:
            self.register(self.events)

    def close(self):
        if self._closed:
            return
        super().close()
        self._closed = True
        self._wbuf, self._rbuf = deque(), deque()

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
            self._rfut.set_result(data)
            self._rfut = None
        else:
            if not data:
                self.close()
            self._rbuf.append(data)
            self._rbsize += len(data)

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
            self._wfut.set_result(bytes_num)
            #self._wfut = None

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
            
    @coroutine
    def read_until(self, regex: str, maxrange: int=None):
        maxrange = maxrange or 65535
        patt = re.compile(tobytes(regex))
        f = Future()
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

    def on_connected(self):
        self._connected = True
        self._wfut.set_result(None)

    def connect(self, addr):
        family = utils.ip_type(addr[0])
        if not family:
            raise ValueError("hostname not support!")
        self._sock = socket.socket(family, socket.SOCK_STREAM)
        self._sock.setblocking(False)
        self._addr = (utils.tostr(addr[0]), addr[1])
        future = Future()
        self._wfut = future
        self.register(self._loop.WRITE)
        try:
            self._sock.connect(self._addr)
        except BlockingIOError:
            pass
        return future

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


class ICMPClient(BaseHandler):

    def __init__(self, loop=None):
        if not loop:
            loop = IOLoop.current()
        super().__init__(loop)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        self._rfut = None
        self.register()

    @coroutine
    def ping(self, dst, timeout=2):

        if not ip_type(dst):
            future =  resolver.getaddrinfo(dst, 0, proto=socket.IPPROTO_ICMP)
            start = time.time()
            timer = self._loop.add_calllater(timeout,
                    lambda: future.cancel((errors.TimeoutError, None, None))
                )
            res = yield future
            self._loop.remove_timer(timer)
            timeout -= (time.time() - start)
            family, tp, proto, cn, sa = res[0]
        else:
            sa = (dst, 0)

        ts = struct.pack("!Q", int(time.time()*1000))
        pkg = cares.build_ping_pkg(ts, 1, 1)
        self._sock.sendto(pkg, sa)
        
        future = self.recvfrom()
        timer = self._loop.add_calllater(
            timeout,lambda: future.cancel((errors.TimeoutError, None, None)))
        res, svr = yield future
        self._loop.remove_timer(timer)

        frame = cares.parse_ping_pkg(res)
        rtt = time.time()*1000 - struct.unpack("!Q", frame.data)[0]
        print("8 bytes from %s: icmp_seq=1 ttl=%d time=%fms" % (svr[0], frame.ip_ttl, rtt))


    def handle(self, sock, fd, events):
        if events & self._loop.ERROR:
            print("icmp socket eroor")
            self.close()
        if events& self._loop.READ:
            self.on_read()

    def on_read(self):
        res = self._sock.recvfrom(65535)
        if self._rfut:
            self._rfut.set_result(res)

    def close(self):
        self._sock.close()
        self._rfut = None
        self._loop.unregister(self._sock)

    def recvfrom(self):
        future = Future()
        self._rfut = future
        return future