import os, time
from cares import rc4 as crc4

data = os.urandom(100)
key = os.urandom(512)

def testpy(count):
    start = time.time()
    for i in range(count):
        en = rc4(data, key)
        de = rc4(en, key)
        #assert data == de
    print("py: ", time.time() - start)

def testc(count):
    start = time.time()
    for i in range(count):
        en = crc4(data, key)
        de = crc4(en, key)
        #assert data == de
        
    print("c : ", time.time() - start)


def rc4(text, key=b"abcd"):
    array = bytearray(text)
    keylen = len(key)
    S = list(range(256))
    j = 0
    for i, v in enumerate(S):
        j = (j + S[i] + key[i % keylen]) % 256
        S[i], S[j] = S[j], S[i]
    i, j = 0, 0
    for n, b in enumerate(array):
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        k = b ^ S[ (S[i] + S[j])  % 256]
        array[n] = k
    return bytes(array)

if __name__ == "__main__":
    count = 100000000
    #testpy(count)
    testc(count)