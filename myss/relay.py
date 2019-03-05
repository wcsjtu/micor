import struct
import os
import socket
import logging
from functools import lru_cache
from . import encryptor, pac, socks5

from micor import TCPClient, coroutine, \
    Connection, IOLoop, Datagram, UDPClient
from micor import errors, utils
from micor.resolvers.poll import resolver

local_addr = "127.0.0.1"
local_port = 1080

server_addr = "127.0.0.1"
server_port = 8850

key = b'123456'

@lru_cache(100)
def udp_client(host, port, family):
    sock = socket.socket(family, socket.SOCK_DGRAM)
    sock.setblocking(False)
    client = UDPClient(sock, (host, port))
    return client


class CmdUDPForward(Exception):pass


class TCPRelayBase(Connection):

    CMD_CONNECT = 0x01
    CMD_BIND = 0x02
    CMD_UDPFWD = 0x03

    LOCAL = False

    def __init__(self, sock, addr, loop):
        super().__init__(sock, addr, loop)
        self.peer = None
        self.encryptor = encryptor
        self.pac = pac.rules
        self.resolver = resolver
        self.is_peer_direct = not self.LOCAL    # 与peer是否直连, server肯定是直连, local要看情况
                                                # 在pac中的就不是直连, 不在的就是直连

    @coroutine
    def create_peer(self, host: str, port: int, atyp: int):
        addr = (host, port)
        conn = TCPClient()
        yield conn.connect(addr)
        logging.debug("TCP: create tcp connect to %s:%d" % addr)
        self.peer = conn
        return conn

    def get_server(self, host: str, port: int):
        direct = self.check_peer_direct(host)
        if direct or (not self.LOCAL):
            return (host, port)
        return (server_addr, server_port)

    def check_peer_direct(self, peerhost):
        if peerhost in self.pac and self.LOCAL:
            self.is_peer_direct = False
        else:
            self.is_peer_direct = True
        return self.is_peer_direct
        
    @coroutine
    def nego(self):
        try:
            chunk = yield self.read_forever(timeout=60)
            yield self.write(self.nego_response())
            return True
        except errors.ConnectionClosed:
            logging.warn(
                "TCP: connect closed by client({:15s}:{:5d}) "\
                "during relay nego".format(*self._addr))
            return False

    @coroutine
    def send_udpfwd_ack(self) -> int:
        if self._sock.family == socket.AF_INET6:
            header = b'\x05\x00\x00\x04'
        else:
            header = b'\x05\x00\x00\x01'
        addr, port = self._sock.getsockname()[:2]
        addr_to_send = socket.inet_pton(self._sock.family, addr)
        port_to_send = struct.pack("!H", port)
        resp = header + addr_to_send + port_to_send
        n = yield self.write(resp)
        return n

    @coroutine
    def syn(self):
        try:
            sks, chunk = yield self.parse_header()
            if self.LOCAL:
                n = yield self.write(socks5.ack(local_addr, local_port))   # send sck

            dest_addr = sks.dest_addr.decode("utf-8")
            svr = self.get_server(dest_addr, sks.dest_port)

            yield self.create_peer(svr[0], svr[1], sks.atyp)    # 连到目标服务器, 可能是代理, 也可能是真正的服务器

            if not self.is_peer_direct:                         # 如果连的是代理, 那么要发送syn信息
                n = yield self.peer.write(
                    self.encryptor.encrypt(chunk, key)
                )
            return True
        except CmdUDPForward:
            n = yield self.send_udpfwd_ack()
            return False
        except errors.ConnectionClosed:
            logging.warn(
                "TCP: connect closed by client({:15s}:{:5d}) "\
                "during relay syn".format(*self._addr))
            return False
        except errors.TimeoutError:
            logging.warn(
                "TCP: relay syn with client "\
                "{:15s}:{:5d} timeout".format(*self._addr))
            return False

    @coroutine
    def relay(self):

        if self.LOCAL:
            res = yield self.nego()
            if not res:
                self.close()
                return

        res = yield self.syn()
        if not res:
            self.close()
            return
        logging.debug("TCP: SYN complete with {:15s}:{:5d}".format(*self.peer._addr))
        while True:
            try:
                chunk = yield self.read_forever(timeout=60)
                logging.debug("TCP: recv {:6d} B from {:15s}:{:5d}".format(len(chunk), *self._addr))
                if self.need_dencrypt():        
                    chunk = self.encryptor.encrypt(chunk, key)      # 这里encrypt==decrypt

                n = yield self.peer.write(chunk)
                logging.debug("TCP: send {:6d} B to   {:15s}:{:5d}".format(n, *self.peer._addr))

                resp = yield self.peer.read_forever(timeout=60)
                logging.debug("TCP: recv {:6d} B from {:15s}:{:5d}".format(len(resp), *self.peer._addr))

                if self.need_dencrypt():
                    resp = self.encryptor.decrypt(resp, key)        # 这里encrypt==decrypt
                
                n = yield self.write(resp)
                logging.debug("TCP: send {:6d} B to   {:15s}:{:5d}".format(n, *self._addr))

            except errors.ConnectionClosed as exc:
                logging.warn("TCP: relay chain broken by {:15s}:{:5d}".format(*exc.by))
                self.close()
                self.peer.close()
                break

    def nego_response(self):
        return b'\x05\x00'

    @coroutine
    def parse_header(self):
        n = 8 if self.LOCAL else 5
        chunk = yield self.read_nbytes(n, timeout=60)
        if self.LOCAL:
            cmd = chunk[1]
            if cmd == self.CMD_UDPFWD:
                logging.debug("udp forward")
                raise CmdUDPForward()
            elif cmd == self.CMD_CONNECT:
                chunk = chunk[3:]       # ss protocol
            else:
                raise RuntimeError("unknown socks5 command: %d" % cmd)
        else:
            chunk = self.encryptor.decrypt(chunk, key)
        h = socks5.parse_socks5_header(chunk)
        chunkpart = yield self.read_nbytes(0 - h.header_length, 20)
        if not self.LOCAL:
            tmp = os.urandom(n) + chunkpart
            chunkpart = self.encryptor.decrypt(tmp, key)[n:]
        chunk += chunkpart
        sks = socks5.parse_socks5_header(chunk)
        return sks, chunk

    def need_dencrypt(self):
        """
        SERVER永远是直连的
        如果不是LOCAL, 也就是SERVER, 需要将LOCAL发过来的数据解密, 然后将目标服务器
        的响应加密发给LOCAL。
        如果LOCAL不是直连, 那么需要将客户端发过来的数据加密, 然后将SERVER发过来的数据
        解密。
        """
        return not (self.is_peer_direct and self.LOCAL)


class SocksTCPLocalRelay(TCPRelayBase):

    LOCAL = True


class SocksTCPServerRelay(TCPRelayBase):
    LOCAL = False


class SocksUDPRelay(Datagram):

    def __init__(self, sock, addr, data, loop=None):
        if not loop:
            loop = IOLoop.current()
        super().__init__(sock, addr, data, loop)
        self.peer = None
        self.encryptor = encryptor
        self.pac = pac.rules
        self.resolver = resolver
        self.is_direct = False

    def get_server(self, host: str, port: int):
        raise NotImplementedError("duty of subclass")

    @coroutine
    def create_peer(self, host: str, port: int, atyp: int):
        family = socks5.ATYP_TO_FAMILY[atyp]
        info = yield self.resolver.getaddrinfo(host, port, family)
        af, _, _, _, sa = info[0]
        logging.debug("UDP: %s resolved into %s" % (host, sa[0]))
        self.peer = udp_client(sa[0], sa[1], af)
        return self.peer

    @coroutine
    def relay(self):
        raise NotImplementedError("duty of subclass")


class SocksUDPLocalRelay(SocksUDPRelay):

    def get_server(self, host: str, port: int):
        if host not in self.pac:
            return (host, port)     # direct conn
        return (server_addr, server_port)

    @coroutine
    def relay(self):
        data = self.read_package()  # recv from client
        if data[2] != 0:
            logging.warn("UDP: drop a message since frag is not 0")
            return
        else:
            data = data[3:]

        sks = socks5.parse_socks5_header(data)

        if sks.dest_port == 0: raise RuntimeError("fail")
        
        dest_addr = sks.dest_addr.decode("utf-8")
        svr_addr = self.get_server(dest_addr, sks.dest_port)

        if dest_addr in self.pac:
            data = self.encryptor.encrypt(data, key)
        else:
            data = data[sks.header_length:]

        yield self.create_peer(svr_addr[0], svr_addr[1], sks.atyp)
        
        self.peer.write(data, svr_addr)     # write encoded text to server
        res, svr = yield self.peer.read(timeout=60)     # recv from server

        logging.debug("UDP: recv {:6d} B from {:15s}:{:5d} ".format(len(res), *svr))
        if not res: return
        
        if dest_addr in self.pac:
            data = self.encryptor.decrypt(data, key)
            res = b'\x00\x00\x00' + data

        self.write_package(res)     # send back to client

        logging.debug("UDP: send {:6d} B to   {:15s}:{:5d} ".format(
            len(res), *self._addr))


class SocksUDPServerRelay(SocksUDPRelay):

    def get_server(self, host, port):
        return (host, port)

    @coroutine
    def relay(self):
        data = self.read_package()      # recv from local
        
        data = self.encryptor.decrypt(data, key)    # decrypt
        sks = socks5.parse_socks5_header(data)      # parse protocol

        if sks.dest_port == 0: raise RuntimeError("fail")

        dest_addr = sks.dest_addr.decode("utf-8")
        svr_addr = self.get_server(dest_addr, sks.dest_port)
        data = data[sks.header_length:]

        yield self.create_peer(svr_addr[0], svr_addr[1], sks.atyp)
        
        self.peer.write(data, svr_addr)     # send to target server
        res, svr = yield self.peer.read(timeout=60) # recv from target server

        logging.debug("UDP: recv {:6d} B from {:15s}:{:5d} ".format(len(res), *svr))
        if not res: return

        if len(self._addr[0]) > 255: raise RuntimeError("bad addr")

        data = socks5.pack_addr(self._addr[0]) + \
            struct.pack("!H", self._addr[1]) + data

        res = self.encryptor.encrypt(data, key)     # encrypt response of target server

        self.write_package(res)     # send back to local
        logging.debug("UDP: send {:6d} B to   {:15s}:{:5d} ".format(
            len(res), *self._addr))