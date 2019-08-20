import select
import heapq
import time
from functools import partial
from collections import defaultdict, deque
from .gen import Future

class SelectImpl:

    def __init__(self):
        self._r_list = set()
        self._w_list = set()
        self._x_list = set()

    def poll(self, timeout):
        r, w, x = select.select(self._r_list, self._w_list, self._x_list, timeout)
        results = defaultdict(lambda: 0x00)
        for p in [(r, IOLoop.READ), (w, IOLoop.WRITE), (x, IOLoop.ERROR)]:
            for fd in p[0]:
                results[fd] |= p[1]
        return results.items()

    def register(self, fd, mode: int):
        if mode & IOLoop.READ:
            self._r_list.add(fd)
        if mode & IOLoop.WRITE:
            self._w_list.add(fd)
        if mode & IOLoop.ERROR:
            self._x_list.add(fd)

    def unregister(self, fd):
        if fd in self._r_list:
            self._r_list.remove(fd)
        if fd in self._w_list:
            self._w_list.remove(fd)
        if fd in self._x_list:
            self._x_list.remove(fd)

    def modify(self, fd, mode):
        self.unregister(fd)
        self.register(fd, mode)

    def close(self):
        pass


try:
    from select import epoll as PollImpl
except:
    PollImpl = SelectImpl


class IOLoop:

    READ = _EPOLLIN = 0x001
    WRITE = _EPOLLOUT = 0x004
    ERROR = 0x008 | 0x010

    TIMEOUT = 10

    DEFAULT_HANDLER = (None, 0, None)

    _instance = None

    @classmethod
    def current(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._stop = False
        self._ready = deque()
        self._timers = list()
        self._timer_cancels = 0
        self._fds = dict()
        self._impl = PollImpl()

    def add_callsoon(self, callback, *args, **kwargs):
        fn = partial(callback, *args, **kwargs)
        self._ready.append(fn)

    def add_calllater(self, delay: int, cb):
        timer = Timer(time.time() + delay, cb)
        self._timers.append(timer)
        return timer

    def add_timer(self, timer):
        self._timers.append(timer)

    def remove_timer(self, timer):
        timer.callback = None
        self._timer_cancels += 0

    def add_future(self, future, callback):

        def cb(fut):
            return self.add_callsoon(callback, fut)

        future.add_done_callback(cb)

    def register(self, sock, mode, handler):
        fd = sock.fileno()
        if fd in self._fds:
            if self._fds[fd][1] != mode:
                self._impl.modify(fd, mode | self.ERROR)
            item = list(self._fds[fd])
            item[2] = handler
            item[1] = mode
            self._fds[fd] = tuple(item)
        else:
            self._fds[fd] = (sock, mode, handler)
            self._impl.register(fd, mode)
        return

    def unregister(self, sock):
        fd = sock.fileno()
        self._fds.pop(fd, None)
        try:
            self._impl.unregister(fd)
        except Exception as err:
            pass

    def mod_register(self, sock, events):
        fd = sock.fileno()
        self._impl.modify(fd, events | self.ERROR)

    def stop(self):
        self._stop = True
        self._ready = None
        self._timers = list()
        self._fds = dict()
        self._impl.close()
        self._timer_cancels = 0

    def run_ready(self):
        while self._ready:
            cb = self._ready.popleft()
            cb()

    def check_due_timer(self):

        if self._timers:
            now = time.time()
            while self._timers:
                if self._timers[0].callback is None:
                    heapq.heappop(self._timers)
                    self._timer_cancels -= 1
                elif self._timers[0].due <= now:
                    self._ready.append(heapq.heappop(self._timers).callback)
                else:
                    break
            
            if (self._timer_cancels > 512 and 
                    self._timer_cancels > (len(self._timers) >> 1)):
                self._timer_cancels = 0
                self._timers = [t for t in self._timers if t.callback is not None]
                heapq.heapify(self._timers)

    def run(self):
        while not self._stop:
            if self._ready:
                self.run_ready()
            self.check_due_timer()
            timeout = self.TIMEOUT
            if self._ready:
                timeout = 0
            elif self._timers:
               delta = self._timers[0].due - time.time()
               timeout = max(0, delta)

            events = self._impl.poll(timeout=timeout)
            for fd, event in events:
                sock, mode, handler = self._fds.get(fd, self.DEFAULT_HANDLER)
                if not sock:
                    continue
                handler(sock, fd, event)
        return None


class Timer(object):

    def __init__(self, due: float, callback):
        self.due = due
        self.callback = callback

    def __lt__(self, other):
        return self.due < other.due

    def __le__(self, other):
        return self.due <= other.due

    def register(self):
        IOLoop.current().add_timer(self)


def sleep(t):
    if t <= 0:
        return sched()
    future = Future()
    due = time.time() + t
    timer = Timer(due, lambda: future.set_result(None))
    timer.register()
    return future

def sched():
    """release CPU and schedule other coroutines to run manually"""
    future = Future()
    loop = IOLoop.current()
    loop.add_callsoon(lambda: future.set_result(None))
    return future    