from collections import deque
from .ioloop import IOLoop
from .gen import Future, coroutine


class Lock:

    def __init__(self, loop: IOLoop=None):
        self._waiters = deque()
        self._locked = False
        if not loop:
            loop = IOLoop.current()
        self._loop = loop

    @coroutine
    def acquire(self):

        future = Future()

        if not self._locked:
            self._locked = True
            self._loop.add_callback(lambda f: f.set_result(True), future)
        else:
            self._waiters.append(future)
        yield future
        return self._locked

    @coroutine
    def release(self):
        future = Future()
        self._loop.add_callback(lambda f: f.set_result(True), future)
        self._locked = bool(self._waiters)
        if self._waiters:
            fut = self._waiters.popleft()
            fut.set_result(True)
        yield future
        return True