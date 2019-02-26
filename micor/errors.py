#coding:utf-8

from concurrent.futures import TimeoutError,\
    CancelledError

class ConnectionClosed(Exception):
    
    def __init__(self, by: tuple, reason: str=""):
        super().__init__()
        self.by = by
        self.reason = reason
