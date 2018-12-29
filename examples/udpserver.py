#coding:utf-8
import sys
sys.path.insert(0, "..")

from src.ioloop import IOLoop, sleep
from src.gen import Future, coroutine
from src.handler import UDPServer
from src.utils import tobytes


class Greeting(UDPServer):

    @coroutine
    def handle_datagram(self, datagram, addr):
        data = datagram.read_package()
        print(data)
        yield sleep(0.5)
        datagram.write_package(data)
        datagram.close()

if __name__ == "__main__":
    loop = IOLoop.current()
    server = Greeting("0.0.0.0", 9111, loop=loop)
    print("listen 0.0.0.0:9111")
    loop.run()
