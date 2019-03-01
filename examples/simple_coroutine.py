from types import GeneratorType
from functools import partial, wraps
from collections import deque

class Scheduler:
    def __init__(self):
        self._ready = deque()
        self._not_ready = deque()

    def add_callsoon(self, cb, *args, **kw):
        fn = partial(cb, *args, **kw)
        self._ready.append(fn)

    def run(self):
        while self._ready:
            cb = self._ready.popleft()
            cb()

scheduler = Scheduler()

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

@coroutine
def show_list(data):
    for v in data:
        print(v)
        future = Future()
        scheduler.add_callsoon(
            lambda: future.set_result(None)
            )
        yield future

if __name__ == "__main__":
    case1 = [1, 2, 3, 4, 5, 6]
    case2 = ["a", "b", "c", "d", "e", "f"]
    show_list(case1)
    show_list(case2)
    scheduler.run()