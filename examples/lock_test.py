#coding:utf-8
import time
import sys
sys.path.insert(0, "..")

from micor.sync import Lock
from micor.gen import coroutine
from micor.ioloop import IOLoop, sleep


lock = Lock()

def ts2str(ts, fmt="%Y-%m-%d %H:%M:%S"):
   return time.strftime(fmt, time.localtime(ts))


def show(*args):
    now = ts2str(time.time())
    print(now, ": ", *args)

@coroutine
def test_lock(tag):
    yield lock.acquire()
    show(tag, " acquire lock")
    yield sleep(5)
    show(tag, " release lock")
    yield lock.release()

if __name__ == "__main__":
    test_lock("netease")
    test_lock("tencent")
    test_lock("baidu")
    test_lock("jingdong")
    IOLoop.current().run()