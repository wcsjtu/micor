from src import Connection， coroutine
from src import errors

class TCPRelay(Connection):

    def __init__(self, sock, addr, loop):
        super().__init__(sock, addr, loop)
        self.peer = None

    @coroutine
    def relay(self):
        while True:
            try:
                chunk = yield self.read_forever()
            except errors.ConnectionClosed:
                break