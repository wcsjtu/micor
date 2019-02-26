#coding: utf-8


class PAC:

    def contains(self, host: str) -> bool:
        return True

    def __contains__(self, key: str):
        return self.contains(key)

rules = PAC()