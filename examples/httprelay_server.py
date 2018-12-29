#coding:utf-8
import sys
sys.path.insert(0, "..")

from urllib.parse import urlsplit
from src.ioloop import IOLoop, sleep
from src.gen import Future, coroutine
from src.handler import TCPServer, Connection, TCPClient
from src.utils import tobytes

from blockio import http_frame


class Relay(TCPServer):

    """
    example:
        telnet 127.0.0.1 9111
        head http://www.baidu.com/
    """

    @coroutine
    def handle_conn(self, conn, addr):
        data = yield conn.read_until(b'\r\n')
        data = data.decode("utf8")
        method, url = data.rstrip("\r\n").split(" ")
        print(method, " ", url)
        res = yield self.fetch(method, url)
        yield conn.write(res)
        conn.close()

    @coroutine
    def fetch(self, method, url):
        site = urlsplit(url)
        addr = (site.hostname, site.port or 80)
        client = TCPClient(addr)
        yield client.connect()
        data = http_frame(method, url, "")
        count = yield client.write(data)
        resp = yield client.read_until(b'\r\n\r\n')
        client.close()
        return resp


if __name__ == "__main__":
    loop = IOLoop.current()
    server = Relay("0.0.0.0", 9111, loop=loop)
    print("listen 0.0.0.0:9111")
    loop.run()