import select
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

    DEFAULT_HANDLER = (None, None)

    _instance = None

    @classmethod
    def current(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._stop = False
        self._ready = deque()
        self._timer = list()
        self._fds = dict()
        self._impl = PollImpl()

    def add_callsoon(self, callback, *args, **kwargs):
        fn = partial(callback, *args, **kwargs)
        self._ready.append(fn)

    def add_timer(self, timer):
        self._timer.append(timer)

    def add_future(self, future, callback):

        def cb(fut):
            return self.add_callsoon(callback, fut)

        future.add_done_callback(cb)

    def register(self, sock, mode, handler):
        fd = sock.fileno()
        self._fds[fd] = (sock, handler)
        self._impl.register(fd, mode)

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
        self._timer = list()
        self._fds = dict()
        self._impl.close()

    def run_ready(self):
        while self._ready:
            cb = self._ready.popleft()
            cb()

    def check_due_timer(self):
        now = time.time()
        todo = []
        while self._timer:
            timer = self._timer.pop()
            if timer.due <= now:
                self._ready.append(timer.callback)
            else:
                todo.append(timer)
        self._timer = todo

    def run(self):
        while not self._stop:
            if self._ready:
                self.run_ready()
            self.check_due_timer()
            timeout = self.TIMEOUT
            if self._ready:
                timeout = 0
            elif self._timer:
               self._timer.sort()
               delta = self._timer[0].due - time.time()
               timeout = max(0, delta)
            events = self._impl.poll(timeout=timeout)
            for fd, event in events:
                sock, handler = self._fds.get(fd, self.DEFAULT_HANDLER)
                if not sock:
                    continue
                handler(sock, fd, event)
        return None


class Timer(object):

    def __init__(self, due: float, callback):
        self.due = due
        self.callback = callback
        self.register()

    def __lt__(self, other):
        return self.due < other.due

    def __le__(self, other):
        return self.due <= other.due

    def register(self):
        IOLoop.current().add_timer(self)


def sleep(timeout):
    future = Future()
    due = time.time() + timeout
    Timer(due, lambda: future.set_result(None))
    return future