#coding:utf-8
import os, socket, sys, struct, logging
from src import BaseHandler, IOLoop, Future, coroutine
from src.utils import ip_type
from .parser import DNSParser, RR
from .logger import logger


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

    def resolve_from_cache(self, host, qtype):
        if ip_type(host):
            return [host]

        ips = list()
        if qtype & DNSParser.QTYPE_A:
            ips = self._hosts_v4.get(host)
            if not ips:
                ips = self._resolved_v4.get(host)
        if qtype & DNSParser.QTYPE_AAAA:
            ips = self._hosts_v6.get(host)
            if not ips:
                ips = self._resolved_v6.get(host)
        return ips

    def _send_req(self, host: bytes, qtype: int):
        req = DNSParser.build_request(host, qtype)
        for server in self._dnsservers:
            self._sock.sendto(req, (server, 53))

    @coroutine
    def getaddrinfo(self, host: str, port, family=socket.AF_INET, type=0, proto=0, flags=0):
        future = Future()
        qtype = self._FAMILY2QTYPE[family]
        host = host.encode("utf-8")
        ips = self.resolve_from_cache(host, qtype)
        if ips:
            logger.debug("hit cache: %s" % host.decode("utf8"))
            self._loop.add_callsoon(lambda f: f.set_result(None), future)
            yield future
        else:
            if qtype & DNSParser.QTYPE_A:
                self._send_req(host, DNSParser.QTYPE_A)
                self._add_to_container(self._futures_v4, host, future)
            if qtype & DNSParser.QTYPE_AAAA:
                self._send_req(host, DNSParser.QTYPE_AAAA)
                self._add_to_container(self._futures_v6, host, future)
            ips = yield future
        if not ips:
            raise socket.gaierror("getaddrinfo failed: %s" % host)
        res = [(family, type, proto, "", (ip, port)) for ip in ips]
        return res

    def on_read(self, data: bytes):
        try:
            hostname, rrs = DNSParser(data).parse_response()
        except Exception as e:
            logging.warn("DNS: parse dns response error: %s" % str(e), exc_info=True)
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
            logging.warn("DNS: dns sock error")
            return
        if events & self._loop.READ:
            try:
                data, server = self._sock.recvfrom(65535)
                self.on_read(data)
            except Exception as exc:
                logging.warn(exc)
            
    def close(self):
        pass


resolver = AsyncResolver()