#coding:utf-8
import sys
sys.path.insert(0, "..")

from urllib.parse import urlsplit
from src.ioloop import IOLoop, sleep
from src.gen import Future, coroutine
from src.handler import TCPServer, Connection, TCPClient
from src.utils import tobytes
from src.errors import ConnectionClosed

class SimpleHTTPServer(TCPServer):

    def response_builder(self, code, data):
        assert code == 200      # 懒得处理其他情况了
        resp = b"HTTP/1.1 200 OK\r\n"\
        b"Content-Type: text/html; charset=utf-8\r\n"\
        b"Server: mirco\r\n"\
        b"Content-Length: %d\r\n"\
        b"\r\n"\
        b"%s" % (len(data), data)
        return resp

    @coroutine
    def handle_conn(self, conn, addr):
        while True:
            try:
                data = yield conn.read_until(b'\r\n\r\n')
                res = self.response_builder(200, b"hello world")
                yield conn.write(res)
            except ConnectionClosed:
                break
        return 0


if __name__ == "__main__":
    loop = IOLoop.current()
    server = SimpleHTTPServer("0.0.0.0", 9111, loop=loop)
    print("listen 0.0.0.0:9111")
    loop.run()

"""
ab -n 100 -c 10 http://localhost:9111/

Server Software:        mirco
Server Hostname:        localhost
Server Port:            9111

Document Path:          /
Document Length:        11 bytes

Concurrency Level:      10
Time taken for tests:   0.058 seconds
Complete requests:      100
Failed requests:        0
Total transferred:      10500 bytes
HTML transferred:       1100 bytes
Requests per second:    1728.34 [#/sec] (mean)
Time per request:       5.786 [ms] (mean)
Time per request:       0.579 [ms] (mean, across all concurrent requests)
Transfer rate:          177.22 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    0   0.4      0       2
Processing:     2    5   3.0      4      14
Waiting:        1    5   3.0      4      13
Total:          3    5   2.9      4      14

Percentage of the requests served within a certain time (ms)
  50%      4
  66%      5
  75%      6
  80%      7
  90%     10
  95%     14
  98%     14
  99%     14
 100%     14 (longest request)
"""