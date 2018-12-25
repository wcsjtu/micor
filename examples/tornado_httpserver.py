#coding:utf8
from tornado.ioloop import IOLoop
from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError
from tornado import gen

class Greeting(TCPServer):

    @gen.coroutine
    def handle_stream(self, stream, address):
        data = yield stream.read_until(b'\r\n\r\n')
        res = self.response_builder(200, b"hello world")
        yield stream.write(res)
        stream.close()

    def response_builder(self, code, data):
        assert code == 200      # 懒得处理其他情况了
        resp = b"HTTP/1.1 200 OK\r\n"\
        b"Content-Type: text/html; charset=utf-8\r\n"\
        b"Server: mirco\r\n"\
        b"Content-Length: %d\r\n"\
        b"\r\n"\
        b"%s" % (len(data), data)
        return resp


if __name__ == "__main__":
    server = Greeting()
    server.listen(9112)
    IOLoop.current().start()

"""
ab -n 100 -c 10 http://localhost:9112/

Server Software:        TornadoServer/5.0.2
Server Hostname:        localhost
Server Port:            9112

Document Path:          /
Document Length:        11 bytes

Concurrency Level:      10
Time taken for tests:   0.088 seconds
Complete requests:      100
Failed requests:        0
Total transferred:      20600 bytes
HTML transferred:       1100 bytes
Requests per second:    1138.93 [#/sec] (mean)
Time per request:       8.780 [ms] (mean)
Time per request:       0.878 [ms] (mean, across all concurrent requests)
Transfer rate:          229.12 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    0   0.2      0       1
Processing:     1    7  16.1      4      86
Waiting:        0    7  16.1      4      86
Total:          1    8  16.2      4      87

Percentage of the requests served within a certain time (ms)
  50%      4
  66%      5
  75%      5
  80%      5
  90%      6
  95%      8
  98%     87
  99%     87
 100%     87 (longest request)
"""