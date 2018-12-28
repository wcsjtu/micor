from types import GeneratorType
from functools import partial, wraps
import time


class Scheduler:
    def __init__(self):
        self._ready = []
        self._not_ready = []

    def add_callsoon(self, cb, *args, **kw):
        fn = partial(cb, *args, **kw)
        self._ready.append(fn)

    def check_due_timer(self):
        now = time.time()
        not_ready = []
        while self._not_ready:
            timer = self._not_ready.pop()
            if timer.due <= now:
                self._ready.append(timer.callback)
            else:
                not_ready.append(timer)
        self._not_ready = not_ready

    def run(self):
        while True:
            while self._ready:
                cb = self._ready.pop()  # 不断地取出cb, 并执行
                cb()
            self.check_due_timer()      # 检查有没有到期的timer, 有的话把它的回调加到_ready里
            if self._ready:
                sleeptime = 0           # 如果_ready不为空, 则一秒钟都不能等, 所以这里必须为0
            elif self._not_ready:
                now = time.time()
                self._not_ready.sort()  # 按due的大小排序, 排在最前的是最快要发生的timer
                delta = self._not_ready[0].due - now    # 如果_not_ready不为空的话, 则
                sleeptime = max(0, delta)               # 需要等待delta秒
            else:
                sleeptime = 10                          # 默认等待时间
            time.sleep(sleeptime)       # 因为没有事情做, 为了节省CPU, 这里选择把线程挂起

scheduler = Scheduler()


class Timer:
    def __init__(self, due: float, callback):
        self.due = due
        self.callback = callback
        scheduler._not_ready.append(self)   # 将timer添加到scheduler的_not_ready队列里

    def __lt__(self, other):
        return self.due < other.due

    def __le__(self, other):
        return self.due <= other.due


class Future:
    def __init__(self):
        self._done = False
        self._callbacks = []
        self._result = None

    def add_done_callback(self, cb):
        self._callbacks.append(cb)

    def set_result(self, r):
        self._result = r
        self.set_done()

    def set_done(self):
        self._done = True
        for cb in self._callbacks:
            cb(self)

def _next(gen, future, value=None):
    try:
        val = value if not value else value._result
        fut = gen.send(val)
        fut.add_done_callback(lambda v: _next(gen, future, v))
    except StopIteration as exc:
        future.set_result(exc.value)

def coroutine(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        future = Future()
        gen = func(*args, **kwargs)
        if isinstance(gen, GeneratorType):
            _next(gen, future)
            return future
        future.set_result(gen)
        return future
    return wrapper

def sleep(timeout):
    future = Future()
    due = time.time() + timeout
    Timer(due, lambda: future.set_result(None))
    return future

@coroutine
def show_list(data):
    for v in data:
        print(v)
        future = Future()
        scheduler.add_callsoon(
            lambda: future.set_result(None)
            )
        yield sleep(0)

@coroutine
def test():
    print(time.time(), " start")        # 1
    yield sleep(5)                      # 2
    print(time.time(), " stop")         # 3

if __name__ == "__main__":
    case1 = [1, 2, 3, 4, 5, 6]
    case2 = ["a", "b", "c", "d", "e", "f"]
    show_list(case1)
    show_list(case2)
    test()
    scheduler.run()