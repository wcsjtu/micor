import sys
from functools import wraps
from types import GeneratorType
import traceback
from . import errors


class Future(object):

    _PENDING = 0
    _RUNNING = 1
    _CANCELLED = 2
    _FINISHED = -1

    __slots__ = ["_callback", "_exc_info", "_result", "_status", "_reuse"]

    def __init__(self, reuse:bool=False):
        self._callback = None
        self._exc_info = None
        self._result = None
        self._status = self._PENDING
        self._reuse = reuse

    def print_excinfo(self):
        if self._exc_info:
            tp, val, tb = self._exc_info
            traceback.print_exception(tp, val, tb, chain=False)

    def cancel(self, excinfo=None):
        if self.done():
            return
        self._status = self._CANCELLED
        excinfo = excinfo or (errors.CancelledError, None, None)
        self.set_exc_info(excinfo)
        self._reuse = False     # if cancelled, future can not be reused

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
            if self._reuse:
                self.clear()
            else:
                del self
                return
            
        if self._callback:
            cb = self._callback
            try:
                cb(self)
            except Exception:
                print('Exception in callback %r for %r' % (cb, self))

        self._status = self._FINISHED
        if not self._reuse:
            self._callback = None

    def clear(self):
        """reset this future"""
        self._status = self._PENDING


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


