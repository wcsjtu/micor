#coding:utf8

def create_data(name, count):
    return ["%s   %d" % (name, i) for i in range(count)]
    
def gen(data):
    for i in data:
        yield i

netease = create_data("netease", 5)
tencent = create_data("tencent", 5)

def coroutine():
    gen_netease = gen(netease)
    gen_tencent = gen(tencent)

    while True:
        try:
            print(gen_netease.send(None))       # 必须要手动调用send, 协程才会继续往下执行
            print(gen_tencent.send(None))       # 有没有办法自动调用send呢？
        except StopIteration:
            break

if __name__ == "__main__":
    coroutine()


