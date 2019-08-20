#coding: utf-8
import logging
import sys
import socket

logging.basicConfig(level=logging.DEBUG)


sys.path.insert(0, ".")

from src import IOLoop, coroutine, TCPServer, UDPServer
from myss.relay import SocksTCPServerRelay, SocksUDPServerRelay


class TCPRelayServer(TCPServer):

    @coroutine
    def handle_conn(self, conn: SocksTCPServerRelay, addr):
        yield conn.relay()


class UDPRelayServer(UDPServer):

    @coroutine
    def handle_datagram(self, datagram: SocksUDPServerRelay, addr):
        yield datagram.relay()


if __name__ == "__main__":
    
    loop = IOLoop.current()
    tcp_server = TCPRelayServer(
        "0.0.0.0", 8850, 
        conn_cls=SocksTCPServerRelay, loop=loop)

    udp_server = UDPRelayServer(
        "0.0.0.0", 8850, 
        conn_cls=SocksUDPServerRelay,
        loop=loop)

    logging.debug("listen 0.0.0.0:8850")
    loop.run()