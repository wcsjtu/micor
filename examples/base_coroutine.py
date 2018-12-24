#coding:utf8

import sys
sys.path.insert(0, "..")

from src.gen import coroutine
from src.ioloop import IOLoop, sleep


case1 = [1, 2, 3, 4, 5, 6, 7, 8, 9 ,10]
case2 = ["a", "b", "c", "d", "e", "f", "d"]


@coroutine
def show(case):
    for v in case:
        print(v)
        yield sleep(1)


if __name__ == "__main__":
    show(case1)
    show(case2)
    IOLoop.current().run()