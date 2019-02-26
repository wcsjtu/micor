#coding:utf-8
import socket
import selectors
from urllib.parse import urlsplit
from blockio import http_frame

_impl = selectors.DefaultSelector()

def httpclient(method, url, body, cb):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)     # 非阻塞
    site = urlsplit(url)
    host = site.hostname
    port = site.port or 80
    
    data = http_frame(method, url, body)

    def handle_events(s, e):
        if e & selectors.EVENT_WRITE:
            s.send(data)                # 未做异常处理
            _impl.modify(s, selectors.EVENT_READ, handle_events)
        if e & selectors.EVENT_READ:
            res = s.recv(65535)         # 未做异常处理
            if not res:
                _impl.unregister(s)
                s.close()
            else:
                cb(res)

    _impl.register(sock, selectors.EVENT_READ|selectors.EVENT_WRITE, handle_events)
    try:
        sock.connect((host, port))
    except BlockingIOError:
        pass


if __name__ == "__main__":
    import time
    start = time.time()
    url = "http://www.baidu.com/"
    count = 10
    stopped = False
    i = 0
    def cb(v):
        global i, stopped
        i += 1
        if i == count:
            delta = time.time() - start
            print(v)
            print("time cost: ", delta)
            stopped = True

    for i in range(count):
        httpclient("HEAD", url, "", cb)

    while not stopped:
        events = _impl.select()
        for key, mask in events:
            cb = key.data
            cb(key.fileobj, mask)