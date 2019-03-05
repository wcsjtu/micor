#coding:utf-8
import os, socket, sys, struct, logging
import time
from micor import IOLoop, Future, coroutine
from micor.utils import ip_type
from micor.sync import Queue, Empty
from .dnsparser import DNSParser, RR
from micor import errors


class NamedList:

    ALL_QTYPE = (DNSParser.QTYPE_A, DNSParser.QTYPE_AAAA)

    def __init__(self):
        self._data = {
            DNSParser.QTYPE_A: dict(),      # v4
            DNSParser.QTYPE_AAAA: dict()    # v6
        }

    def set_item(self, host: bytes, item: object, qtype: int):
        for qt in self.ALL_QTYPE:
            if qt & qtype:
                self._add_to_container(self._data[qt], host, item)

    def set_list(self, host: bytes, items: list, qtype):
        for qt in self.ALL_QTYPE:
            if qt & qtype:
                self._data[qt][host] = items
        
    def get(self, host, qtype):
        """return dict whit format {qtype: [ips]}"""
        res = dict()
        for qt in self.ALL_QTYPE:
            if qt & qtype:
                items = self._data[qt].get(host) or list()
                if items:
                    res[qt] = items
        return res

    def _add_to_container(self, container: dict, hostname: str, obj: object):
        l = container.get(hostname) or list()
        l.append(obj)
        container[hostname] = l


class AsyncResolver:
    FAMILY_ALL = 0

    _FAMILY2QTYPE = {
        socket.AF_INET: DNSParser.QTYPE_A,
        socket.AF_INET6: DNSParser.QTYPE_AAAA,
        FAMILY_ALL: DNSParser.QTYPE_A | DNSParser.QTYPE_AAAA
    }
    _QTYPE2FAMILY = {
        DNSParser.QTYPE_A: socket.AF_INET,
        DNSParser.QTYPE_AAAA: socket.AF_INET6,
        DNSParser.QTYPE_A | DNSParser.QTYPE_AAAA : FAMILY_ALL
    }

    def __init__(self, loop=None):
        self._hosts_v4 = dict()
        self._hosts_v6 = dict()

        self._host = NamedList()
        self._resolved = NamedList()
        self._queues = dict()          # {transaction_id: queue}

        self._dnsservers = list()
        self._sock = self.create_sock()
        if not loop:
            loop = IOLoop.current()
        self._loop = loop
        self.load_hosts()
        self.parse_resolv()
        self.register(self._loop.READ, self.handle)

    def register(self, events=None, cb=None):
        if self._sock._closed:
            return
        if events is None:
            events = self._loop.READ | self._loop.ERROR
        else:
            events = self._loop.READ | self._loop.ERROR | events
        if not cb:
            cb = self.handle
        self._loop.register(self._sock, events, cb)

    def create_sock(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
        s.setblocking(False)
        return s

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
                        self._host.set_item(parts[i], ip, self._FAMILY2QTYPE[tp])
        except IOError:
            self._host.set_item(b'localhost', ["127.0.0.1"], DNSParser.QTYPE_A)
            self._host.set_item(b'localhost', ["[::]"], DNSParser.QTYPE_AAAA)

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
            self._dnsservers = ['8.8.8.8']

    def set_server(self, serverlist):
        self._dnsservers = serverlist

    def _addr_from_cache(self, host: bytes, qtype: int):
        """`coroutine`. Get IP address informations from cache, return tuple with 
        format ( {qtype: [ips]}, lack_qtype )"""
        future = Future()
        res = dict()        # family: [iplist]
        family = ip_type(host)
        if family:
            qt = self._FAMILY2QTYPE[family]
            res = {qt: [host]}
        else:
            res = self._resolved.get(host, DNSParser.QTYPE_A | DNSParser.QTYPE_AAAA)

        for qt in res:
            qtype ^= qt     # 检查是否还缺少v4或者v6
        
        self._loop.add_callsoon(lambda: future.set_result((res, qtype)))
        return future

    def _transaction_id(self):
        return struct.unpack("!H", os.urandom(2))[0]

    def _send_req(self, host: bytes, tid: int, qtype: int):
        req = DNSParser.build_request(host, qtype, tid)
        # for server in self._dnsservers:
        #     self._sock.sendto(req, (server, 53))
        self._sock.sendto(req, (self._dnsservers[0], 53))

    @coroutine
    def getaddrinfo(self, 
            host: str, port: int, 
            family: int=0, type: int=0, 
            proto: int=0, flags: int=0,
            timeout: int=10):
        qtype = self._FAMILY2QTYPE[family]
        bhost = host.encode("utf-8")
        typed_ips, qtype = yield self._addr_from_cache(bhost, qtype)
        if qtype:
            qsize = 0
            tid = self._transaction_id()
            if qtype & DNSParser.QTYPE_A:
                self._send_req(bhost, tid, DNSParser.QTYPE_A)
                qsize += 1
            if qtype & DNSParser.QTYPE_AAAA:
                self._send_req(bhost, tid, DNSParser.QTYPE_AAAA)
                qsize += 1
            
            queue = Queue(maxsize=qsize)
            self._queues[tid] = queue
            while qsize:
                if timeout < 0:
                    self._queues.pop(tid, None)
                    raise errors.TimeoutError()
                start = time.time()
                resolved = None
                try:
                    resolved = yield queue.get(timeout=timeout) # {qtype: ips}
                    timeout -= (time.time() - start)
                except Empty:
                    pass
                except Exception as exc:
                    logging.warn("DNS: %s" % exc)
                finally:
                    qsize -= 1
                if resolved is None:
                    logging.warn("DNS: %s resolve failed" % host)
                else:
                    typed_ips.update(resolved)
            self._queues.pop(tid, None)
        else:
            logging.debug("DNS: %s hit cache" % host)

        if not typed_ips:
            raise socket.gaierror("getaddrinfo failed: %s" % host)
        res = []
        for qt, ips in typed_ips.items():
            fm = self._QTYPE2FAMILY[qt]
            res += [(fm, type, proto, "", (ip, port)) for ip in ips]
        return res

    def on_read(self, data: bytes):
        tid = struct.unpack("!H", data[:2])[0]
        queue = self._queues.get(tid, None)
        if not queue:
            logging.warn("DNS: no wait queue found, but received a response with transaction id %d" % tid)
            return
        try:
            hostname, qtype, rrs = DNSParser(data).parse_response()
        except Exception as e:
            logging.warn("DNS: parse dns response error: %s" % str(e), exc_info=True)
            queue.put(None)
            return

        ipv4s, ipv6s = list(), list()
        for rr in rrs:
            if rr.qtype == DNSParser.QTYPE_A and rr.qcls == DNSParser.QCLASS_IN:
                ipv4s.append(rr.value)

            elif rr.qtype == DNSParser.QTYPE_AAAA and rr.qcls == DNSParser.QCLASS_IN:
                ipv6s.append(rr.value)

        if qtype & DNSParser.QTYPE_A:
            self._resolved.set_list(hostname, ipv4s, DNSParser.QTYPE_A)
            queue.put({DNSParser.QTYPE_A: ipv4s})
        if qtype & DNSParser.QTYPE_AAAA:
            self._resolved.set_list(hostname, ipv6s, DNSParser.QTYPE_AAAA)
            queue.put({DNSParser.QTYPE_AAAA: ipv6s})

    def handle(self, sock, fd, events):
        if events & self._loop.ERROR:
            self.close()
            logging.warn("DNS: dns sock error")
            return
        if events & self._loop.READ:
            try:
                data, _ = self._sock.recvfrom(65535)
                self.on_read(data)
            except Exception as exc:
                logging.warn(exc, exc_info=True)
            
    def close(self):
        pass


resolver = AsyncResolver()