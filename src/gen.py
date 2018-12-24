#coding:utf8
import time
from types import GeneratorType
from functools import partial, wraps

class EventList:

    _instance = None

    @classmethod
    def current(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._ready = []
        self._not_ready = []

    def add_callback(self, cb, *args, **kw):
        fn = partial(cb, *args, **kw)
        self._ready.append(fn)

    def add_timer(self, timer):
        self._not_ready.append(timer)

    def _check_not_ready(self):
        now = time.time()
        notready = []
        while self._not_ready:
            timer = self._not_ready.pop()
            if timer.due <= now:
                self._ready.append(timer.callback)
            else:
                notready.append(timer)
        self._not_ready = notready

    def run(self):
        while (self._ready or self._not_ready):
            self._check_not_ready()
            if self._ready:
                cb = self._ready.pop()
                cb()

    
class Future:

    def __init__(self):
        self._done = False      # 状态, 表示是否结束了
        self._callbacks = []    
        self._result = None     # 结果

    def add_done_callback(self, cb):
        self._callbacks.append(cb)

    def set_result(self, r):
        self._result = r
        self.set_done()

    def set_done(self):
        self._done = True
        for cb in self._callbacks:
            cb(self)


class Timer:

    def __init__(self, due, callback):
        self.due = due
        self.callback = callback
        self.register()

    def __lt__(self, other):
        return self.due < other.due

    def __le__(self, other):
        return self.due <= other.due

    def register(self):
        EventList.current().add_timer(self)

def sleep(timeout):
    future = Future()
    due = time.time() + timeout
    Timer(due, lambda: future.set_result(None))
    return future

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


if __name__ == "__main__":
    
    events = EventList.current()

    case1 = [1, 2, 3, 4, 5, 6]
    case2 = ["a", "b", "c", "d", "e", "f", "g"]

    @coroutine
    def show(case):
        for v in case:
            future = Future()
            events.add_callback(lambda: future.set_result(None))
            print(v)
            yield sleep(1)

    show(case1)
    show(case2)

    events.run()
    