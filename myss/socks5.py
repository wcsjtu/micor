#coding: utf-8 
import struct
import socket
from .parser import parse_socks5_header, SocksHeader
from micor.utils import ip_type


def ack(addr: str, port: int) -> bytes:

    family = ip_type(addr)
    if family == socket.AF_INET:
        stype = SocksHeader.ATYP_IPV4
        saddr = socket.inet_pton(family, addr)
    elif family == socket.AF_INET6:
        stype = SocksHeader.ATYP_IPV6
        saddr = socket.inet_pton(family, addr)
    else:
        addr_len = struct.pack("!B", len(addr))
        stype = SocksHeader.ATYP_HOST
        saddr = addr_len + addr.encode("utf-8")

    seq = [
        b'\x05\x00\x00', struct.pack("!B", stype),
        saddr, struct.pack("!H", port)
    ]
    return b"".join(seq)


ATYP_TO_FAMILY = {
    SocksHeader.ATYP_HOST: 0,
    SocksHeader.ATYP_IPV4: socket.AF_INET,
    SocksHeader.ATYP_IPV6: socket.AF_INET6
}

FAMILY_TO_ATYP = {
    socket.AF_INET: SocksHeader.ATYP_IPV4,
    socket.AF_INET6: SocksHeader.ATYP_IPV6
}

def family2atyp(family: int) -> int:
    return FAMILY_TO_ATYP[family]

def atyp2family(atyp: int) -> int:
    return ATYP_TO_FAMILY[atyp]

def pack_addr(addr):
    for family, atyp in FAMILY_TO_ATYP.items():
        try:
            n = socket.inet_pton(family, addr)
            return struct.pack("!B", atyp) + n
        except (TypeError, ValueError, OSError, IOError):
            pass
    res = struct.pack("!BB", SocksHeader.ATYP_HOST, len(addr)) + \
        addr.encode("utf-8")
    return res