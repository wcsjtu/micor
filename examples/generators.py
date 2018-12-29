#coding=utf-8

def gen(name):
    print("GEN : call gen with name=%s" % name)

    val = yield "1st yield from gen "        # val是外面send进来的
    print("GEN : send %s to gen" % val)

    try:
        err = yield "2nd yield from gen "    # 外面会throw异常到这里
        print("GEN : send %s to gen" % err)
    except Exception as exc:
        print("GEN : throw exception to gen: %s" % exc)

    err = yield "3rd yield from gen "                      # 外面会throw异常到这里

    print("GEN : unreachable code in gen")        # 这个是不可能会执行的, 因为上面已经出了异常


if __name__ == "__main__":

    g = gen("hello")
    print("MAIN: 1st send to gen")
    print("MAIN: %s\n" % g.send(None))                         # 第一次yield的值

    print("MAIN: 2nd send to gen")
    print("MAIN: %s\n" % g.send("world"))                      # 第二次yield的值

    print("MAIN: 3rd send to gen")
    print("MAIN: %s\n" % g.throw(RuntimeError, "catched"))     # 第三次yield的值

    try:
        g.throw(RuntimeError, "wtf")                           # 第三次yield的赋值操作
    except StopIteration as err:
        print("MAIN: %s\n" % ("gen returns %s" % str(err)))

    print("MAIN: %s\n" % "unreachable code")