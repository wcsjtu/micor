#coding:utf-8

import socket
from urllib.parse import urlsplit


def http_frame(method, url, body):
    site = urlsplit(url)
    if body:
        content_length = "Content-Length: %d\r\n" % len(body)
    else:
        body = ""
        content_length = ""

    headers = "%s %s HTTP/1.1\r\n"\
    "HOST: %s\r\n"\
    "Connection: keep-alive\r\n"\
    "User-Agent: Mozilla/5.0\r\n"\
    "%s"\
    "\r\n"\
    "%s" % (method.upper(), site.path or "/", site.netloc, content_length, body)
    return headers.encode("utf8")

def httpclient(method, url, body):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    site = urlsplit(url)
    host = site.hostname
    port = site.port or 80
    sock.connect((host, port))

    data = http_frame(method, url, body)

    sock.send(data)
    res = sock.recv(65535)
    sock.close()
    return res

if __name__ == "__main__":

    import time
    start = time.time()

    url = "http://www.baidu.com/"
    for i in range(10):
        res = httpclient("HEAD", url, "")
    print(res)
    delta = time.time() - start
    print("time cost: ", delta)