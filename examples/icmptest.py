import socket, struct, time
import sys
import cares


sys.path.insert(0, ".")
sys.path.insert(0, "..")

from src.handler import BaseHandler
from src import Future, coroutine, IOLoop, errors
from src.utils import ip_type
from myss.resolver import resolver


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


@coroutine
def test_ping(dsts):
    client = ICMPClient()
    for dst in dsts:
        yield client.ping(dst)
    IOLoop.current().stop()

if __name__ == "__main__":

    dsts = [
        "www.baidu.com",
        "115.239.210.27",
        "10.240.228.1",
        "www.google.com"
    ]

    test_ping(dsts)

    IOLoop.current().run()
    



# def ping():
#     ts = struct.pack("!Q", int(time.time()*1000))
#     pkg = cares.build_ping_pkg(ts, 1, 1)
#     print([hex(i) for i in pkg])
#     s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
#     s.sendto(pkg, ("10.240.228.1", 0))
#     res, addr = s.recvfrom(65535)

#     frame = cares.parse_ping_pkg(res)
#     print(socket.inet_ntop(socket.AF_INET,  struct.pack("!I", frame.ip_dst_addr)))
#     print(socket.inet_ntop(socket.AF_INET, struct.pack("!I", frame.ip_src_addr)))
#     print(frame.ip_ttl)
#     print(frame.id)
#     print(frame.seq)
#     print(frame.data)
#     cares.ICMPFrame
#     print(res)

# ping()