import sys
from functools import wraps
from types import GeneratorType
import traceback
from . import errors

def print_exception(tp, val, tb):
    import linecache
    fnames = set()
    tmp = []
    for f, lineno in traceback.walk_tb(tb):
        co = f.f_code
        filename = co.co_filename
        name = co.co_name

        if filename.endswith(__file__):
            continue

        fnames.add(filename)
        linecache.lazycache(filename, f.f_globals)
        tmp.append((filename, lineno, name))

    for filename in fnames:
        linecache.checkcache(filename)

    print("Traceback (most recent call last):", file=sys.stderr)
    for filename, lineno, name in tmp:
        srccode = linecache.getline(filename, lineno).strip()
        print(
            "  File \"%s\", line %d, in %s\n    %s\n" % (
                filename, lineno, name, srccode),
            file=sys.stderr, end=""
                )
    tpv = tp.__qualname__
    smod = tp.__module__
    if smod not in ("__main__", "builtins"):
        tpv = smod + '.' + tpv + ":"
    print(tpv, val, file=sys.stderr)

class Future(object):

    _PENDING = 0
    _RUNNING = 1
    _CANCELLED = 2
    _FINISHED = -1

    __slots__ = ["_callback", "_exc_info", "_result", "_status"]

    def __init__(self):
        self._callback = self.print_excinfo
        self._exc_info = None
        self._result = None
        self._status = self._PENDING

    def print_excinfo(self, fut=None):
        fut = fut if fut else self
        if fut._exc_info:
            tp, val, tb = fut._exc_info
            print_exception(tp, val, tb)

    def cancel(self, excinfo=None):
        if self.done():
            return
        self._status = self._CANCELLED
        excinfo = excinfo or (errors.CancelledError, None, None)
        self.set_exc_info(excinfo)

    def done(self):
        return self._status == self._FINISHED

    def add_done_callback(self, callback):
        self._callback = callback

    def result(self):
        return self._result

    def set_result(self, result):
        self._result = result
        self.set_done()

    def set_exc_info(self, exc_info):
        self._exc_info = exc_info
        self.set_done()

    def set_done(self):

        if self._status == self._FINISHED:
            del self
            return
            
        cb = self._callback
        try:
            cb(self)
        except Exception:
            print('Exception in callback %r for %r' % (cb, self))

        self._status = self._FINISHED
        self._callback = None


def _next(gen, future, value=None):
    try:
        if not value:
            fut = gen.send(value)
        else:
            if value._exc_info:
                fut = gen.throw(*value._exc_info)
            else:
                fut = gen.send(value._result)
        fut.add_done_callback(lambda value: _next(gen, future, value))
    except StopIteration as e:
        future.set_result(e.value)
    except Exception:
        future.set_exc_info(sys.exc_info())
        

def coroutine(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        future = Future()
        try:
            gen = func(*args, **kwargs)
        except Exception:
            future.set_exc_info(sys.exc_info())
            return future
        else:
            if isinstance(gen, GeneratorType):
                _next(gen, future)
                return future
        future.set_result(gen)
        return future

    return wrapper

