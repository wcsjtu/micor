import sys
from functools import wraps
from types import GeneratorType
import traceback


class Future(object):

    __slots__ = ["_callbacks", "_exc_info", "_result", "_done"]

    def __init__(self):
        self._callbacks = list()
        self._exc_info = None
        self._result = None
        self._done = False

    def _print_excinfo(self):
        if self._exc_info:
            tp, val, tb = self._exc_info
            traceback.print_exception(tp, val, tb, chain=False)

    def add_done_callback(self, callback):
        self._callbacks.append(callback)

    def result(self):
        return self._result

    def set_result(self, result):
        self._result = result
        self.set_done()

    def set_exc_info(self, exc_info):
        self._exc_info = exc_info
        self.set_done()

    def set_done(self):
        self._done = True
        if not self._callbacks:
            self._print_excinfo()
            return
            
        for cb in self._callbacks:
            try:
                cb(self)
            except Exception:
                print('Exception in callback %r for %r' % (cb, self))
        self._callbacks = []


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


