import os
import socket
import struct
from typing import List, Tuple

try:
    from .cares import RR
except ImportError:
    
    class RR:
        """resource record of DNS, see https://www.ietf.org/rfc/rfc1035.txt for detail"""

        __slots__ = ["domain_name", "qtype", "qcls", "ttl", "value"]

        def __init__(self, 
                domain_name: bytes, 
                value: bytes,
                qtype: int, 
                qcls: int, 
                ttl: int):
            self.domain_name = domain_name
            self.qtype = qtype
            self.qcls = qcls
            self.ttl = ttl
            self.value = value

try:
    from .cares import DNSParser
except ImportError:
    
    class DNSParser:

        _DOMAIN_END = 0
        _MAX_PART_LENGTH = 63

        QTYPE_A = 1
        QTYPE_NS = 2
        QTYPE_CNAME = 5
        QTYPE_AAAA = 28
        QTYPE_ANY = 255
        QCLASS_IN = 1

        def __init__(self, dns_response: bytes):
            """build a DNS parser with DNS response"""
            self.offset = 0
            self.data = dns_response

        def forward(self, nbytes: int) -> bytes:
            """low-level api
            
            skip n bytes by add `nbytes` to `offset` field
            
            return slice of data"""
            up = self.offset + nbytes
            t = self.data[self.offset:up]
            self.offset = up
            return t

        def parse_domain(self) -> bytes:
            """low-level api
            
            parse domain name from `data`. it will modify `offset` field"""
            d = self.data
            domain_part = []
            up = 0
            i = self.offset
            while d[i] != self._DOMAIN_END:
                length = d[i]
                if length >= 0xc0:
                    if i >= self.offset:
                        self.offset += 2
                    i = struct.unpack("!H", d[i:i+2])[0] -0xc000
                    continue
                up = i + length + 1
                domain_part.append(d[i+1:up])
                if up >= self.offset:
                    self.offset += (length + 1)
                i = up
            if up >= self.offset:
                self.offset += 1
            return b".".join(domain_part)

        @classmethod
        def build_request(cls, hostname: bytes, qtype: int) -> bytes:
            """build DNS request package with hostname and qtype. type of `hostname`
            must be bytes; and qtype must be one of
                `DNSParser.QTYPE_A`
                `DNSParser.QTYPE_AAAA`
                `DNSParser.QTYPE_CNAME`
                `DNSParser.QTYPE_NS`
                `DNSParser.QTYPE_ANY`
            return DNS request package"""
            assert isinstance(hostname, bytes), "hostname must be bytes type"
            count = struct.pack("!HHHH", 1, 0, 0, 0)
            header = os.urandom(2) + b"\x01\x00" + count
            parts = hostname.split(b".")
            qname = []
            for p in parts:
                if len(p) > cls._MAX_PART_LENGTH:
                    raise RuntimeError("invalid DNS response")
                qname += [struct.pack("!B", len(p)), p]
            qname = b''.join(qname) + b"\x00"
            t_c = struct.pack("!HH", qtype, cls.QCLASS_IN)
            question = qname + t_c
            return header + question


        def parse_response(self) -> Tuple[bytes, List[RR]]:
            """high-level api.
            parse DNS resource record from data
            hostname is the same as the one which passed to `build_request` method,
            and its type is bytes.
            
            each item in rrs is an instance of class `RR`"""

            self.forward(6) # skip header
            c = answer_rrs, authority_rrs, addtional_rrs = \
                struct.unpack("!HHH", self.forward(6))
            query_domain = self.parse_domain()
            query_type = self.forward(2)    # skip query type
            query_cls = self.forward(2)     # skip query class
            rrs = []
            for count in c:
                rrs += self._parse_rrs(count)
            return query_domain, rrs

        def _parse_rrs(self, count: int) -> List[RR]:
            """internal method"""
            rs = []
            for i in range(count):
                domain = self.parse_domain()
                qtype, qcls, ttl, data_length = struct.unpack("!HHIH" ,self.forward(10))
                if qtype == self.QTYPE_A:       # ipv4
                    data = socket.inet_ntoa(self.forward(data_length))
                elif qtype == self.QTYPE_AAAA:  # ipv6
                    data = socket.inet_ntop(socket.AF_INET6,self.forward(data_length))
                elif qtype in [self.QTYPE_NS, self.QTYPE_CNAME]:   # cname
                    data = self.parse_domain()
                else:   # other query type, such as SOA, PTR ant etc.
                    data = self.parse_domain()
                record = RR(domain, data, qtype, qcls, ttl)
                rs.append(record)
            return rs

try:
    from .cares import parse_socks5_header
except ImportError:

    def parse_socks5_header(s: bytes) -> SocksHeader:
        """Parse destination addr and port from socks5 header.

        Normally, a SocksHeader instance(means succeed) or 
        `None`(means need more data) will be returned. If parse 
        failed, an exception will be raised"""
        assert isinstance(s, bytes), "a bytes object is required"
        dl = len(s)
        if dl < 5:
            return None

        IPV4_LEN, IPV6_LEN = 7, 19

        atyp = s[0]
        if atyp == SocksHeader.ATYP_IPV4:
            if dl < IPV4_LEN:
                return None
            addr = socket.inet_ntop(socket.AF_INET, s[1:5])
            port = struct.unpack("!H", s[5:7])[0]
            length = IPV4_LEN
        elif atyp == SocksHeader.ATYP_IPV6:
            if dl < IPV6_LEN:
                return None
            addr = socket.inet_ntop(socket.AF_INET6, s[1:17])
            port = struct.unpack("!H", s[17:19])[0]
            length = IPV6_LEN
        elif atyp == SocksHeader.ATYP_HOST:
            addrlen = s[1]
            if dl < 2 + addrlen:
                return None
            addr = s[2:2 + addrlen]
            port = struct.unpack('!H', s[2 + addrlen:4 + addrlen])[0]
            length = 4 + addrlen
        else:
            raise ValueError("invalid qtyp")
        res = SocksHeader(atyp, addr, port, length)
        return res

try:
    from .cares import SocksHeader
except ImportError:
    
    class SocksHeader:

        ATYP_IPV4 = 0x01
        ATYP_HOST = 0x03
        ATYP_IPV6 = 0x04

        __slots__ = ["atyp", "dest_addr", "dest_port", "header_length"]

        def __init__(self, atyp: int, dest_addr: bytes, 
            dest_port: int, header_length: int):

            self.atyp = atyp
            self.dest_addr = dest_addr
            self.dest_port = dest_port
            self.header_length = header_length
