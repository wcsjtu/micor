#coding: utf-8
import socket
import os
import sys
import time
sys.path.insert(0, "..")
from myss.parser import parse_socks5_header
# from cares import parse_socks5_header


def test_socks5():

    d = [
        b'\x01\xc0\xa8\x01d\x1f@' + os.urandom(10),  # ipv4
        b'\x01\xc0\xa8\x01d',  # ipv4, need more

        b'\x04' + socket.inet_pton(socket.AF_INET6, "[::]") + b'\x1f@' + os.urandom(10),  # ipv6
        b'\x04' + b'\x00\x00\x00\x00\x00\x00\x00\x00\x00',   # ipv6 need more

        b'\x03\x0dwww.baidu.com\x1f@' + os.urandom(10),  # host
        b'\x03\x0dwww.baidu.co',    # host need more

        #b'\x09' + os.urandom(10),   # error
    ]

    for i in d:
        r = parse_socks5_header(i)
        # if r:
        #     print(r.dest_addr, r.dest_port)
        # else:
        #     print(r)

def testc(count):
    
    st = time.time()
    for _ in range(count):
        test_socks5()
    print("c : ", time.time() - st)

if __name__ == "__main__":
    count = 100000
    testc(count)
