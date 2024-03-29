#coding:utf-8
import sys
sys.path.insert(0, "..")

from micor.ioloop import IOLoop, sleep
from micor.gen import Future, coroutine
from micor.handler import TCPServer, Connection, TCPClient
from micor.utils import tobytes


class EchoServer(TCPServer):

    @coroutine
    def handle_conn(self, conn, addr):
        data = yield conn.read_until(b"\r\n")
        print(b"client say: " + data)
        yield self.delay(1)
        yield conn.write(b"server say: " + data)
        conn.close()
        return 0

    @coroutine
    def delay(self, t):
        yield sleep(t)
        

if __name__ == "__main__":
    loop = IOLoop.current()
    server = EchoServer("0.0.0.0", 9111, loop=loop)
    print("listen 0.0.0.0:9111")
    loop.run()