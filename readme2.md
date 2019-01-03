# 从生成器到异步IO: 自己实现Python协程框架（二）

上一篇文章中介绍了如何从"零"开始, 写一个协程框架。到目前为止, 这个协程框架已经能够实现多任务之间的协调了, 让多个任务"看起来"是同时执行的。但是还是有很多问题

- 有的情况下, 需要严格控制协程执行的顺序, 也就是协程间的`同步`
- 当在协程函数中调用了`阻塞`的系统调用, 比如说(`sendall`, `recv`), 整个线程会挂起, 从而导致整个服务不可用
- 这玩意有什么用？

以上三点, 就是这篇文章要讲的内容

## 同步

### 背景

先讲简单的同步问题。 思考一下, 协程为什么需要同步, 协程不是单线程的吗, 又不是多线程, 要同步干什么？先看下面这段伪代码

```python
def foo():
    log = open("tmp.log", "w+")     # 文件不能被打开2次
    time.sleep(0)
    log.close()
foo()
foo()
```

非协程的情况下, 调用2次`foo`是没问题的, 因为`open`之前, 一定调用了`log.close()`。 但是对应到协程版本

```python
@coroutine
def foo():
    log = open("tmp.log", "w+")     # 文件不能被打开2次
    yield sleep(0)
    log.close()
foo()
foo()
```

连续调用2次`foo`, 就可能有问题了。因为`yield`关键字把`foo`函数硬生生地拆分为两部分。 `open`和`close`之间, 可能会穿插着其他的操作, 比如说另一个协程的`open`, 这样就会报错了。 所以我们希望的是, `open`和`close`是原子的, 也就是要加锁, 那么对应的伪代码, 就应该长这样

```python
@coroutine
def foo():
    lock.acquire()
    log = open("tmp.log", "w+")
    yield sleep(0)
    log.close()
    lock.release()
```

那么, 这个`lock`, 应该怎么实现呢？

### Lock实现

参考一下线程版`Lock`的实现, 我们期望的Lock行为是

1. Lock有状态, `_locked`表示是否已经被获取了
2. `acquire`方法获取锁, `release`方法释放锁
3. 当`_locked == False`时, 调用`acquire`方法会设置`_locked=True`, 然后立即返回
4. 当`_locked == True`时, 调用`acquire`方法会"阻塞", 也就是不继续往下执行。
5. 调用`release`方法, 在释放锁的同时, 唤醒"阻塞"着的协程, 同时不影响自己继续往下执行

由于4, 所以`acquire`方法必须是协程函数, 因为普通函数根本不能产生"阻塞"的效果; 由于5， 所以`release`方法也必须是协程函数, 因为没有办法在一个函数里"同时"做两件事。

根据上面的分析, 这个Lock类的大致样子我们就知道了

```python
class Lock:
    def __init__(self, sched):
        self._locked = False
        self._sched = sched
        self._waiters = list()

    @coroutine
    def acquire(self):
        future = Future()
        if not self._locked:
            # 如果锁没有被获取, 则先设置状态
            self._locked = True
            # 然后"立即"返回, 至于为什么调用这个函数就能让acquire方法"立即"返回, 请参见前一篇文章的分析
            self._sched.add_callsoon(lambda f: f.set_result(True), future)
        else:
            # 否则, 就把future添加到_waiters队列里, 同时会把调用这个方法的协程"阻塞"住
            # 同样的, 为什么会acquire方法"阻塞", 请参见前一篇文章的分析
            self._waiters.append(future)
        yield future
        return self._locked

    @coroutine
    def release(self):
        future = Future()
        self._sched.add_callsoon(lambda f: f.set_result(True), future)
        self._locked = bool(self._waiters)
        if self._waiters:
            # 如果有协程在等待这个锁释放, 那么就把第一个等待的协程的future对象取出来
            fut = self._waiters.pop()
            # 然后唤醒这个协程, 为什么能唤醒协程, 理由和上面是一样的, 稍微提示一下, 调用下面这句话后
            # 调用链会回到acquire中的yield future这行
            fut.set_result(True)
        yield future
        return True
```

代码非常简单、精炼, 其核心思想就是

- `yield future`语句把方法拆分为上下两部分, 上面的部分会逐行执行, 下面的部分什么时候开始执行, 就要看什么`future.set_result`方法什么时候被调用了。
- 这里一共有两个时机会调用`future.set_result`方法, 一是调用`release`的时候, 二是调度器立马执行(callsoon)

所以, 没有"阻塞"是因为调度器立马就调用了`set_result`, "阻塞"是因为直到`release`时才调用。 是不是很amazing...

最后, 在[examples/lock_test.py](examples/lock_test.py)里有测试例子, 跑下来的结果是

```text
2019-01-03 19:13:19 :  netease  acquire lock
2019-01-03 19:13:24 :  netease  release lock
2019-01-03 19:13:24 :  tencent  acquire lock
2019-01-03 19:13:29 :  tencent  release lock
2019-01-03 19:13:29 :  baidu  acquire lock
2019-01-03 19:13:34 :  baidu  release lock
2019-01-03 19:13:34 :  jingdong  acquire lock
2019-01-03 19:13:39 :  jingdong  release lock
```

大家可以尝试下把加锁/解锁的操作注释掉, 看看结果。

## IO

接下来讲一个稍微复杂点的——IO。 讲到IO, 不得不提一个老生常谈的问题: 同步与异步、阻塞与非阻塞之间的异同。 简单地说

- 阻塞就是当事件没发生时, 一直在那`等着`, 直到事件发生, 再处理这个事件
- 非阻塞就是当事件没发生时, `不等`, 直接去做别的事情。至于什么时候回过头来处理这个事件, 天知道...
- 同步就是事件发生时, 有人通知我, 我`可以去处理`这个事件了(还是tm要我处理)
- 异步就是事件发生时, 有人通知我, 这个事件`已经处理好了`...

所以, 同步/异步这一组概念, 与阻塞/非阻塞这一组概念, 没半毛钱关系。但是, 在网络编程领域, 这两个概念经常被混用。 而且, 在诸多事件模型中, 只有Windows的IOCP勉强算是异步IO, 其他的都只是非阻塞IO(对, 包括大名鼎鼎的epoll)。 在这样的现实面前, 我们就勉强把异步和非阻塞划等号吧

```txt
                        异步 ≈ 非阻塞
```

现在就先看个Python的阻塞(同步?)IO的例子

### 阻塞IO

详细代码在[blockio.py](examples/blockio.py)文件里, 这里只说下我们要关注的部分

```python
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((host, port))              # 阻塞
data = http_frame(method, url, body)
sock.send(data)                         # 阻塞
res = sock.recv(65535)                  # 阻塞
```

上面的代码, 有三处会阻塞

- `connect`, 要等待TCP 三次握手完成
- `send`, 要收到对端回复的`ack`
- `recv`, 要等待对端发数据过来

在等待过程中, 线程会挂起, 什么都不能做, 所以特别浪费时间。 可以跑一下blockio.py这个脚本, 看下访问10次百度首页的时间开销

```text
time cost:  0.1506052017211914
```

这个时间看着不长, 但是对比下非阻塞IO的数据后, 就能看出差距了。

### 非阻塞IO

在Python里, 要把一个`文件描述符`(fd), 或者说`socketobj`变成非阻塞模式, 非常简单, 一行代码就能搞定

```python
import socket
socketobj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
socketobj.setblocking(False)    # 非阻塞模式
```

就这么一行, 就能把`socketobj`设置成非阻塞模式。 但是, 仅仅变成非阻塞是没有卵用的, 反而会让代码变得复杂, 因为读数据可能一次性读不完, 写数据也写不完...最要命的是, 根本不知道什么时候可写/读, 随便写/读的话, 分分钟报错给你看。 [`IO多路复用`](https://www.zhihu.com/question/32163005)技术就是为了解决这些问题出现的

### MultiplexingIO

从实现层面上来讲, IO多路复用就是用一个线程, 来监听多个文件描述符的状态/事件, 一旦状态有变化/事件触发, 就会执行对应的回调函数。 如果不用IO多路复用的话, 要想同时操作多个fd, 必须要开多线程。 IO多路复用中, 最核心的一个概念就是`事件模型`, 它负责着事件的监听与通知。现有的事件模型有这么几种

- select
- poll
- epoll
- iocp

这些模型之间的区别, 这里就不讲了, 不然篇幅太长。 只需要知道, 在Python3里面, 已经对这些模型做了封装, 我们可以直接调用——[selectors](https://docs.python.org/3/library/selectors.html), 这个模块可以根据当前的平台, 自动选择最优的事件模型。

这个模块的用法也很简单

```python
import selectors
_impl = selectors.DefaultSelector()

# 事件注册
_impl.register(
    sock,           # 文件描述符, 也就是要监听的socket对象
    selectors.EVENT_READ | selectors.EVENT_WRITE,   # 这个是要监听的事件, 这里同时监听读和写事件
    handle_events   # 事件触发后的回调函数
    )

while True:
    events = _impl.select(10)   # 开始监听, 有事件触发或者超时, 这个函数就会返回
    for key, mask in events:    # 取出事件
        cb = key.data
        cb(key.fileobj, mask)   # 执行对应的回调
```

用法很简单, 直接注册、监听就可以了。 但是有三个地方要注意, 先说简单的

> _impl.select(10)

这个`select`方法有一个特性, 就是执行后, 线程会挂起, 直到有事件发生, 或者超时(这里设置的是10秒), 返回触发的事件或者空。超时这个特性, 与`sleep`函数倒是很像, 大家有没有想到什么...

> WRITE, READ事件究竟何时触发

从字面意义上来看, 就是`可读`、`可写`的时候触发, 那究竟何时`可写`/`可读`呢？考虑到IO一般是网络IO, 这个事件肯定与传输层的状态有关。 所以, 这里贴一张大名鼎鼎的TCP状态机

![tcp_state_machine.jpeg](resources/tcp&#32;state&#32;machine.jpeg)

我们就分析这张图上的, 哪些状态对应着 READ/WRITE事件。(PS: 对于epoll而言, 有水平触发和边缘触发两种情况, 两种情况下的事件还不太一致, 我们这里只讨论水平触发)

- READ事件

SYN-RCVD -> ESTABLISHED, 这个状态变化只会发生在服务端, 表示有个客户端完成了TCP三次握手, 建立了连接, 此时listen的socket变得可读, 可以调用`accept`方法会返回一个socket对象来描述该连接

ESTABLISHED 状态下, 对端有数据发送过来, 此时连接socket会变得可读, 调用`read`方法就能获取到对端发过来的数据

ESTABLISHED -> CLOSE_WAIT, 这个状态变化, 表示对端关闭了连接的写通道(也就是不再发数据了), 此时连接socket会变得可读, 调用`read`方法会返回`空字符串`。 一般情况下, 不会出现半连接的状态, 所以可以暴力的认为, `read() == ""`时, 连接被对方断开了。

还有一种情况, 在图中没有, 但是也会变得可读。 这种情况就是, 当对端程序崩溃时, 会发送`RST`过来, 此时连接socket也会可读, 但是调用`read`方法, 会报错, 在windows下, 就是errno 10054; 在Chrome显示, 就是`连接被重置`, 有木有很熟悉, 伟大的GFW就是这么干的, 冒充服务器给你发个`RST`...

- WRITE事件

SYN-SENT -> ESTABLISHED, 这个状态变化只会发生在客户端, 表示已经和服务端完成了TCP三次握手, 建立好了连接, 此时socket就会变得可写。 在`ESTABLISHED`之前, 任何尝试写socket的操作, 都会报错

ESTABLISHED, 这个状态下的socket, 一直处于可写状态。这里就有个问题, 如果连接建立后, 监听了WRITE事件, 那么WRITE事件会一直触发, 如果有数据要写, 那没什么问题, 如果没有, 那就是在浪费CPU了。所以, `WRITE事件, 只在有需要的情况下才去监听`, 比如说, write_buffer里有数据时, 才去监听WRITE事件, write_buffer空了, 就取消监听WRITE事件。

> 回调函数应该怎么写

对应的回调函数, 应该接受两个参数(s, e)

- s是一个socket对象, 表示在哪个socket上触发了事件, e表示触发了什么事件
- e是一个整数, 表示发生了哪些事件

要判断是否发生了READ事件, 只需要判断`e & selectors.EVENT_READ`是否为`true`就行了。 所以, 一个简单的回调函数可以这么写

```python
def handle_events(s: socket.socket, e: int):
    if e & selectors.EVENT_WRITE:
        s.send(data)        # 未做异常处理
        _impl.modify(s, selectors.EVENT_READ, handle_events)    # 取消对WRITE事件的监听
    if e & selectors.EVENT_READ:
        res = s.recv(65535)         # 未做异常处理
        if not res:                 # 没有读到数据, 说明对端关闭了连接
            _impl.unregister(s)     # 取消注册
            s.close()               # 关闭连接, 也就是发送FIN
        else:
            cb(res)                 # 读到了数据, 想怎么处理就怎么处理
```

这个回调函数中, `send`和`recv`都没有做异常处理, 在实际使用中, 这两个方法经常报`异常`, 比如一下写的数据太多, 把socket的缓冲区写满了, 或者说读的时候, 对方根本没发送那么多的数据过来, 这两种情况, 都会报`EAGAIN`的异常, 意思就是, 等会再来...

说了这么多, 这玩意到底有什么用。 还是以访问10次百度首页为例子, 测试下用了IO多路复用后的时间开销, 代码文件在[examples/multiplexingio.py](examples/multiplexingio.py), 直接用python3运行的结果是

```text
time cost:  0.024246931076049805
```

和之前阻塞IO的结果对比, 提升是非常明显的。 而且请求越多, 这种效果就越明显。

## 新的调度器

还是那个经典的问题: epoll这玩意有什么用？回忆一下上面说过的, `select`方法的特性

> 执行后, 线程会挂起, 直到有事件发生, 或者超时(这里设置的是10秒), 返回触发的事件或者空

这个简直就是高级版的`sleep`啊, 又能延时执行, 又能处理IO事件。 所以, 把IO多路复用加到之前的调度器中, 这样我们就有了一个新的调度器, 给它改个名字, 叫`IOLoop`

为了方便注册socket, 给它加几个方法/属性

```python
class IOLoop:
    ... # 重复的代码就不写了
    self._impl = selectors.DefaultSelector()

    def register(self, sock, events, handler):
        self._impl.register(sock, events, handler)

    def unregister(self, sock):
        self._impl.unregister(sock)

    def run(self):
        while True:
            ... # 重复的代码就不写了
            # time.sleep(sleeptime)
            events = self._impl.select(sleeptime)
            for key, mask in events:
                cb = key.data
                cb(key.fileobj, mask)
```

现在就把之前的调度器, 与IO完美的结合在一起了。 这部分完整的代码在[src/ioloop.py](src/ioloop.py)里, 和这里的代码稍微有点不一样, 因为没有用selectors模块。

那么, 还是那个经典的问题: 这玩意有什么用？

## 用处

既然有了协程框架和异步IO, 那么我们就可以用协程的写法, 来写网络服务器、客户端、代理等等。 这兼顾了IO复用的高性能和协程的友好写法——不用去写回调了...相信每个写过JS的人, 都能够记起当年被callback hell所支配的恐惧。

话放在这了, 但是代码应该怎么写呢？ 其实也不难, 就是[examples/multiplexingio.py](examples/multiplexingio.py)中`handle_events`函数的拆分与扩充。

### TCP服务器

对于TCP服务器来说, 有两种socket对象

- 监听socket, 负责监听端口, 同时与客户端建立连接
- 连接socket, 代表着一个与客户端的连接

对于监听socket来说, 它的事件处理非常简单, 因为它只有`READ`事件和`ERROR`事件, 出现`ERROR`事件后, 直接关闭socket即可

```python
class TCPServer:
    def handle(self, sock, fd, events):
        if events & self._loop.ERROR:
            # 如果监听socket异常了, 直接关闭socket
            self.close()
            raise Exception('server_socket error')
        try:
            conn, addr = self._sock.accept()        # 建立连接

            # 生成连接对象, 所以的读写操作都是在这个对象里完成的, 下面会详细介绍
            h = Connection(conn, addr, self._loop)

            # 这个函数就是处理业务逻辑的, 必须在子类实现它, 它必须返回一个Future  
            future = self.handle_conn(h, addr)
            if future is not None:
                self._loop.add_future(future, lambda f: f.set_result(None))
        except (OSError, IOError) as exc:
            print("accept error: ", exc)
```