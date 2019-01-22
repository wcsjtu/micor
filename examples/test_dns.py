import sys

sys.path.insert(0, "..")

from myss.resolver import AsyncResolver
from src.gen import coroutine, Future
from src import IOLoop

@coroutine
def test():
    resolver = AsyncResolver()
    hostname = b"www.baidu.com"
    result = yield resolver.getaddrinfo(hostname, 80)
    print(result)
    IOLoop.current().stop()

if  __name__ == "__main__":
    test()
    IOLoop.current().run()
