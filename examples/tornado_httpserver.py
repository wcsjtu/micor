#coding:utf8
import tornado
import tornado.web
from tornado.web import RequestHandler
from tornado.web import Application

class Greeting(RequestHandler):

    def get(self, *args, **kwargs):
        self.write(b"hello world")
        self.finish()


if __name__ == "__main__":
    app = Application(
        [(r"^/$", Greeting)]
    )
    app.listen(9112, "0.0.0.0")
    tornado.ioloop.IOLoop.current().start()

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