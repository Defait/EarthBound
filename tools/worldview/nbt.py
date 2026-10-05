"""Minimal read-only NBT parser (Java Edition, big-endian).

Compounds become dicts, lists become Python lists, and the three array
tags become numpy arrays so block-state data can be unpacked quickly.
"""
import struct

import numpy as np

_BYTE = struct.Struct(">b")
_SHORT = struct.Struct(">h")
_USHORT = struct.Struct(">H")
_INT = struct.Struct(">i")
_LONG = struct.Struct(">q")
_FLOAT = struct.Struct(">f")
_DOUBLE = struct.Struct(">d")


class _Reader:
    __slots__ = ("buf", "pos")

    def __init__(self, buf):
        self.buf = buf
        self.pos = 0

    def string(self):
        (n,) = _USHORT.unpack_from(self.buf, self.pos)
        self.pos += 2
        s = self.buf[self.pos:self.pos + n].decode("utf-8", errors="replace")
        self.pos += n
        return s

    def payload(self, tag):
        buf = self.buf
        if tag == 10:
            out = {}
            while True:
                t = buf[self.pos]
                self.pos += 1
                if t == 0:
                    return out
                name = self.string()
                out[name] = self.payload(t)
        if tag == 8:
            return self.string()
        if tag == 1:
            v = _BYTE.unpack_from(buf, self.pos)[0]
            self.pos += 1
            return v
        if tag == 3:
            v = _INT.unpack_from(buf, self.pos)[0]
            self.pos += 4
            return v
        if tag == 9:
            t = buf[self.pos]
            (n,) = _INT.unpack_from(buf, self.pos + 1)
            self.pos += 5
            return [self.payload(t) for _ in range(n)]
        if tag == 12:
            (n,) = _INT.unpack_from(buf, self.pos)
            self.pos += 4
            v = np.frombuffer(buf, dtype=">i8", count=n, offset=self.pos)
            self.pos += 8 * n
            return v
        if tag == 2:
            v = _SHORT.unpack_from(buf, self.pos)[0]
            self.pos += 2
            return v
        if tag == 4:
            v = _LONG.unpack_from(buf, self.pos)[0]
            self.pos += 8
            return v
        if tag == 5:
            v = _FLOAT.unpack_from(buf, self.pos)[0]
            self.pos += 4
            return v
        if tag == 6:
            v = _DOUBLE.unpack_from(buf, self.pos)[0]
            self.pos += 8
            return v
        if tag == 7:
            (n,) = _INT.unpack_from(buf, self.pos)
            self.pos += 4
            v = np.frombuffer(buf, dtype=np.int8, count=n, offset=self.pos)
            self.pos += n
            return v
        if tag == 11:
            (n,) = _INT.unpack_from(buf, self.pos)
            self.pos += 4
            v = np.frombuffer(buf, dtype=">i4", count=n, offset=self.pos)
            self.pos += 4 * n
            return v
        raise ValueError(f"unknown NBT tag {tag} at offset {self.pos}")


def loads(data):
    """Parse an uncompressed NBT blob and return its root compound."""
    r = _Reader(memoryview(data).tobytes() if not isinstance(data, bytes) else data)
    tag = r.buf[0]
    r.pos = 1
    if tag != 10:
        raise ValueError(f"root tag is {tag}, expected compound")
    r.string()  # root name, usually empty
    return r.payload(10)
