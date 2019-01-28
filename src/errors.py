#coding:utf-8

from concurrent.futures import TimeoutError,\
    CancelledError

class ConnectionClosed(Exception):
    pass
