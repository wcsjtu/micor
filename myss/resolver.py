#coding:utf-8
import os, socket, sys, struct, logging
from src import BaseHandler, IOLoop, Future, coroutine
from src.utils import ip_type

class InvalidDomainName(Exception):pass


class RR(object):
    """resource record"""

    __slots__ = ["domain_name", "qtype", "qcls", "ttl", "value"]

    def __init__(self, dn, qt, qc, ttl, val):
        self.domain_name = dn
        self.qtype = qt
        self.qcls = qc
        self.ttl = ttl
        self.value = val


class Response(object):
    DOMAIN_END = 0

    def __init__(self, d):
        self._offset = 0
        self._data = d

    def cut(self, i):
        up = self._offset + i
        t = self._data[self._offset:up]
        self._offset = up
        return t

    def __getitem__(self, i):
        return self._data[i]

    def cut_domain(self):
        """get domain from repsonse, return doamin 
        string and its length in protocol"""
        d = self._data
        domain_part = []
        up = 0
        i = self._offset
        while d[i] != self.DOMAIN_END:
            length = d[i]
            if length >= 0xc0:
                if i >= self._offset:
                    self._offset += 2
                i = struct.unpack("!H", d[i:i+2])[0] -0xc000
                continue
            up = i + length + 1
            domain_part.append(d[i+1:up])
            if up >= self._offset:
                self._offset += (length + 1)
            i = up
        if up >= self._offset:
            self._offset += 1
        return b".".join(domain_part)


class DNSParser(object):

    QTYPE = (QTYPE_A, QTYPE_NS, QTYPE_CNAME, QTYPE_AAAA, QTYPE_ANY) = \
        (1, 2, 5, 28, 255)

    QTYPE_IP = (QTYPE_A, QTYPE_AAAA)

    MAX_PART_LENGTH = 63

    QCLASS_IN = 1


    def build_request(self, hostname: bytes, qtype):
        count = struct.pack("!HHHH", 1, 0, 0, 0)
        header = os.urandom(2) + b"\x01\x00" + count
        parts = hostname.split(b".")
        qname = []
        for p in parts:
            if len(p) > self.MAX_PART_LENGTH:
                raise InvalidDomainName(p)
            qname += [struct.pack("!B", len(p)), p]
        qname = b''.join(qname) + b"\x00"
        t_c = struct.pack("!HH", qtype, self.QCLASS_IN)
        question = qname + t_c
        return header + question

    def parse_response(self, response: bytes):
        resp = Response(response)
        resp.cut(6)     # ID and question number
        answer_rrs, authority_rrs, addtional_rrs = \
            struct.unpack("!HHH", resp.cut(6))
        query_domain = resp.cut_domain()
        query_type = resp.cut(2)
        query_cls = resp.cut(2)

        arrs = self.parse_rrs(resp, answer_rrs)
        aurrs = self.parse_rrs(resp, authority_rrs)
        adrrs = self.parse_rrs(resp, addtional_rrs)
        rrs = arrs + aurrs + adrrs
        return query_domain.decode("utf-8"), rrs

    def parse_rrs(self, resp, rrs):
        rs = []
        for i in range(rrs):
            domain = resp.cut_domain()
            qtype, qcls, ttl, data_length = struct.unpack("!HHIH" ,resp.cut(10))
            if qtype == self.QTYPE_A:       # ipv4
                data = socket.inet_ntoa(resp.cut(data_length))
            elif qtype == self.QTYPE_AAAA:  # ipv6
                data = socket.inet_ntop(socket.AF_INET6,resp.cut(data_length))
            elif qtype in [self.QTYPE_NS, self.QTYPE_CNAME]:   # cname
                data = resp.cut_domain()
            else:   # other query type, such as SOA, PTR ant etc.
                data = resp.cut_domain()
            record = RR(domain, qtype, qcls, ttl, data)
            rs.append(record)
        return rs


class AsyncResolver(BaseHandler):

    _FAMILY2QTYPE = {
        socket.AF_INET: DNSParser.QTYPE_A,
        socket.AF_INET6: DNSParser.QTYPE_AAAA,
        0: DNSParser.QTYPE_A | DNSParser.QTYPE_AAAA
    }

    def __init__(self, loop=None):
        self._hosts_v4 = dict()
        self._hosts_v6 = dict()
        self._resolved_v4 = dict()  # {hostname: iplist}
        self._resolved_v6 = dict()
        self._futures_v4 = dict()      # {hostname: futurelist}
        self._futures_v6 = dict()      # {hostname: futurelist}
        self._dnsservers = list()
        self._sock = self.create_sock()
        self._parser = DNSParser()
        if not loop:
            loop = IOLoop.current()
        self._loop = loop
        self.load_hosts()
        self.parse_resolv()
        self.register(self._loop.READ, self.handle)

    def create_sock(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
        s.setblocking(False)
        return s


    def _add_to_container(self, container: dict, hostname: str, obj: object):
        l = container.get(hostname, list())
        l.append(obj)
        container[hostname] = l

    def load_hosts(self):
        if 'WINDIR' in os.environ:
            hostsfile = os.environ['WINDIR'] + '/system32/drivers/etc/hosts'
        else:
            hostsfile = "/etc/hosts"

        try:
            with open(hostsfile, "rb") as f:
                for line in f.readlines():
                    parts = line.strip().split()
                    l = len(parts)
                    if l < 2: 
                        continue
                    ip = parts[0]
                    tp = ip_type(ip)
                    if not tp: 
                        continue
                    for i in range(1, l):
                        if not parts[i]: 
                            continue
                        container = self._hosts_v4 if tp == socket.AF_INET else self._hosts_v6
                        self._add_to_container(container, parts[i], ip)
        except IOError:
            self._hosts_v4["localhost"] = ["127.0.0.1"]
            self._hosts_v6["localhost"] = ["[::]"]

    def parse_resolv(self):
        try:
            with open('/etc/resolv.conf', 'rb') as f:
                content = f.readlines()
                for line in content:
                    line = line.strip()
                    if line and line.startswith(b'nameserver'):
                        parts = line.split()
                        if len(parts) >= 2:
                            server = parts[1]
                            if ip_type(server) == socket.AF_INET:
                                server = server.decode('utf8')
                                self._dnsservers.append(server)
        except IOError:
            pass
        if not self._dnsservers:
            self._dnsservers = ['8.8.4.4', '8.8.8.8']

    def reslove_from_cache(self, host, qtype):
        ips = list()
        if qtype & self._parser.QTYPE_A:
            ips = self._hosts_v4.get(host)
            if not ips:
                ips = self._resolved_v4.get(host)
        if qtype & self._parser.QTYPE_AAAA:
            ips = self._hosts_v6.get(host)
            if not ips:
                ips = self._resolved_v6.get(host)
        return ips

    def _send_req(self, host: str, qtype: int):
        host = host.encode("utf-8")
        req = self._parser.build_request(host, qtype)
        for server in self._dnsservers:
            self._sock.sendto(req, (server, 53))

    @coroutine
    def getaddrinfo(self, host, port, family=socket.AF_INET, type=0, proto=0, flags=0):
        future = Future()
        qtype = self._FAMILY2QTYPE[family]
        ips = self.reslove_from_cache(host, qtype)
        if ips:
            self._loop.add_callsoon(lambda f: f.set_result(None), future)
            yield future
        else:
            if qtype & self._parser.QTYPE_A:
                self._send_req(host, self._parser.QTYPE_A)
                self._add_to_container(self._futures_v4, host, future)
            if qtype & self._parser.QTYPE_AAAA:
                self._send_req(host, self._parser.QTYPE_AAAA)
                self._add_to_container(self._futures_v6, host, future)
            ips = yield future
        if not ips:
            raise socket.gaierror("getaddrinfo failed: %s" % host)
        res = [(family, type, proto, "", (ip, port)) for ip in ips]
        return res

    def on_read(self, data: bytes):
        try:
            hostname, rrs = self._parser.parse_response(data)
        except Exception as e:
            logging.warn("parse dns response error: %s" % str(e), exc_info=True)
            return 
        ipv4s, ipv6s = list(), list()
        for rr in rrs:
            if rr.qtype == DNSParser.QTYPE_A and rr.qcls == DNSParser.QCLASS_IN:
                ipv4s.append(rr.value)
            elif rr.qtype == DNSParser.QTYPE_AAAA and rr.qcls == DNSParser.QCLASS_IN:
                ipv6s.append(rr.value)
        v4_futures = self._futures_v4.pop(hostname, [])
        v6_futures = self._futures_v6.pop(hostname, [])
        for future in v4_futures:
            future.set_result(ipv4s)
        for future in v6_futures:
            future.set_result(ipv6s)

    def handle(self, sock, fd, events):
        if events & self._loop.ERROR:
            self.close()
            print("dns sock error")
            return
        if events & self._loop.READ:
            try:
                data, server = self._sock.recvfrom(65535)
                self.on_read(data)
            except Exception as exc:
                print(exc)
            

            
    def close(self):
        pass