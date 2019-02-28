from collections import deque
from queue import Empty, Full
from .ioloop import IOLoop
from .gen import Future, coroutine


class Lock:

    def __init__(self, loop: IOLoop=None):
        self._waiters = deque()
        self._locked = False
        if not loop:
            loop = IOLoop.current()
        self._loop = loop

    def acquire(self):
        future = Future()
        if not self._locked:
            self._locked = True
            self._loop.add_callsoon(lambda f: f.set_result(True), future)
        else:
            self._waiters.append(future)
        return future

    def release(self):
        future = Future()
        self._loop.add_callsoon(lambda f: f.set_result(True), future)
        self._locked = bool(self._waiters)
        if self._waiters:
            fut = self._waiters.popleft()
            fut.set_result(True)
        return future


class Queue:

    def __init__(self, maxsize=0):
        self._loop = IOLoop.current()
        self._items = deque()
        self._item_count = 0
        self._maxsize = maxsize
        self._get_waiters = deque()
        self._put_waiters = deque()
        self._timers = dict()   # id(future): timer
        self._putter_cache = dict()     # id(future): item

    def _wakeup_first_getter(self, item):
        future = self._get_waiters.popleft()
        timer = self._timers.pop(id(future), None)
        if timer:
            self._loop.remove_timer(timer)
        future.set_result(item)

    def _wakeup_first_putter(self):
        future = self._put_waiters.popleft()
        idfut = id(future)
        timer = self._timers.pop(idfut, None)
        if timer:
            self._loop.remove_timer(timer)
        item = self._putter_cache.pop(idfut)
        self._items.append(item)
        self._item_count += 1
        future.set_result(None)


    def get(self, block=True, timeout=0):
        
        future = Future()
        if self._item_count > 0:
            item = self._items.popleft()
            self._item_count -= 1
            self._loop.add_callsoon(lambda: future.set_result(item))
            if self._put_waiters:
                self._wakeup_first_putter()
            return future
        
        if not block:
            raise Empty

        def on_time():
            future.set_exc_info((Empty, None, None))
            self._get_waiters.remove(future)
             
        if timeout and timeout > 0:
            timer = self._loop.add_calllater(timeout, on_time)
            self._timers[id(future)] = timer
        self._get_waiters.append(future)
        return future

    def full(self):
        return self._maxsize > 0 and self._item_count >= self._maxsize

    def empty(self):
        return self._item_count == 0

    def qsize(self):
        return self._item_count

    def put(self, item, block=True, timeout=None):
        future = Future()

        if self._get_waiters:
            self._wakeup_first_getter(item)
            self._loop.add_callsoon(lambda: future.set_result(None))
            return future
        
        if not self.full():
            self._items.append(item)
            self._item_count += 1
            self._loop.add_callsoon(lambda: future.set_result(None))
            return future

        if not block:
            raise Full

        def on_timeout():
            self._putter_cache.pop(id(future), None)
            future.set_exc_info((Full, None, None))
            self._put_waiters.remove(future)        # TODO, too slow

        if timeout and timeout > 0:
            timer = self._loop.add_calllater(timeout, on_timeout)
            self._timers[id(future)] = timer

        self._putter_cache[id(future)] = item
        self._put_waiters.append(future)
        return future