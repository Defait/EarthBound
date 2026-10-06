"""A reader for FTB Quests' SNBT files (the writer is in build.py).

FTB's SNBT is NBT's text form as FTB Library writes it: compounds with unquoted or quoted keys, values
separated by newlines or commas, typed numbers (1b, 2L, 0.5d), true/false. Numbers come back as
int or float (the type suffix is dropped), lists as lists, compounds as dicts.
"""
import re

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?([bBsSlLfFdD]?)")
_BARE = re.compile(r"[A-Za-z0-9_\-.+:/]+")
_KEY = re.compile(r"[A-Za-z0-9_\-.+]+")


class SnbtError(ValueError):
    pass


def loads(text):
    p = _Parser(text)
    value = p.value()
    p.skip()
    if p.i != len(p.s):
        raise SnbtError(f"trailing data at {p.where()}")
    return value


class _Parser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def where(self):
        line = self.s.count("\n", 0, self.i) + 1
        return f"line {line}"

    def skip(self):
        s, n = self.s, len(self.s)
        while self.i < n and (s[self.i] in " \t\r\n,"):
            self.i += 1

    def peek(self):
        self.skip()
        return self.s[self.i] if self.i < len(self.s) else ""

    def value(self):
        c = self.peek()
        if c == "{":
            return self.compound()
        if c == "[":
            return self.list()
        if c in "\"'":
            return self.string()
        m = _NUM.match(self.s, self.i)
        if m and m.end() > self.i and (m.end() == len(self.s) or not _BARE.match(self.s[m.end()])):
            self.i = m.end()
            text = m.group(0)
            suffix = m.group(1)
            body = text[:-1] if suffix else text
            if (suffix and suffix in "fFdD") or "." in body or "e" in body.lower():
                return float(body)
            return int(body)
        m = _BARE.match(self.s, self.i)
        if not m:
            raise SnbtError(f"unexpected {c!r} at {self.where()}")
        self.i = m.end()
        word = m.group(0)
        return {"true": True, "false": False}.get(word, word)

    def string(self):
        q = self.s[self.i]
        self.i += 1
        out = []
        while True:
            c = self.s[self.i]
            if c == "\\":
                nxt = self.s[self.i + 1]
                out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                self.i += 2
            elif c == q:
                self.i += 1
                return "".join(out)
            else:
                out.append(c)
                self.i += 1

    def key(self):
        c = self.peek()
        if c in "\"'":
            return self.string()
        m = _KEY.match(self.s, self.i)
        if not m:
            raise SnbtError(f"expected a key at {self.where()}")
        self.i = m.end()
        return m.group(0)

    def compound(self):
        self.i += 1
        out = {}
        while True:
            if self.peek() == "}":
                self.i += 1
                return out
            k = self.key()
            if self.peek() != ":":
                raise SnbtError(f"expected ':' after {k!r} at {self.where()}")
            self.i += 1
            out[k] = self.value()

    def list(self):
        self.i += 1
        if re.match(r"[BIL];", self.s[self.i:self.i + 2]):
            self.i += 2
        out = []
        while True:
            if self.peek() == "]":
                self.i += 1
                return out
            out.append(self.value())
