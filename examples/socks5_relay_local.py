#coding: utf-8
import logging
import sys
import socket

logging.basicConfig(level=logging.DEBUG)


sys.path.insert(0, ".")

from src import IOLoop, coroutine, TCPServer, UDPServer
from myss.relay import SocksTCPLocalRelay, SocksUDPLocalRelay


class TCPRelayServer(TCPServer):

    @coroutine
    def handle_conn(self, conn: SocksTCPLocalRelay, addr):
        yield conn.relay()


class UDPRelayServer(UDPServer):

    @coroutine
    def handle_datagram(self, datagram: SocksUDPLocalRelay, addr):
        yield datagram.relay()


if __name__ == "__main__":
    
    loop = IOLoop.current()
    tcp_server = TCPRelayServer(
        "0.0.0.0", 1080, 
        conn_cls=SocksTCPLocalRelay, loop=loop)

    udp_server = UDPRelayServer(
        "0.0.0.0", 1080, 
        conn_cls=SocksUDPLocalRelay,
        loop=loop)

    logging.debug("listen 0.0.0.0:1080")
    loop.run()