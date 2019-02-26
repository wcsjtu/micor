#coding: utf-8

from .parser import rc4


def encrypt(text: bytes, key: bytes) -> bytes:
    return rc4(text, key)



def decrypt(text: bytes, key: bytes) -> bytes:
    return rc4(text, key)