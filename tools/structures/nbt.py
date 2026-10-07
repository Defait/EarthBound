"""Typed NBT for structure templates and Easy NPC presets: binary read/write (gzip) and SNBT parse/format.

Python values map to NBT tags as follows; the subclasses keep the exact tag type through a read-modify-write:
    Byte, Short, Int, Long (int subclasses), Float, Double (float subclasses), str -> String,
    dict -> Compound, List (list subclass, optional element type) -> List, ByteArray / IntArray / LongArray.
Plain int becomes Int, plain float Double, bool Byte, plain list a List of its first element's type.
"""
import gzip
import io
import re
import struct


class Byte(int): pass
class Short(int): pass
class Int(int): pass
class Long(int): pass
class Float(float): pass
class Double(float): pass
class ByteArray(list): pass
class IntArray(list): pass
class LongArray(list): pass


class List(list):
    """An NBT list; `kind` is the element tag id (inferred from the first element when None)."""
    def __init__(self, items=(), kind=None):
        super().__init__(items)
        self.kind = kind


END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY, LONG_ARRAY = range(13)


def tag_id(v):
    if isinstance(v, bool) or isinstance(v, Byte):
        return BYTE
    if isinstance(v, Short):
        return SHORT
    if isinstance(v, Long):
        return LONG
    if isinstance(v, int):
        return INT
    if isinstance(v, Float):
        return FLOAT
    if isinstance(v, float):
        return DOUBLE
    if isinstance(v, str):
        return STRING
    if isinstance(v, ByteArray):
        return BYTE_ARRAY
    if isinstance(v, IntArray):
        return INT_ARRAY
    if isinstance(v, LongArray):
        return LONG_ARRAY
    if isinstance(v, dict):
        return COMPOUND
    if isinstance(v, list):
        return LIST
    raise TypeError(f"no NBT tag for {type(v).__name__}: {v!r}")


# ------------------------------------------------------------------ binary
def _w_string(out, s):
    b = s.encode("utf-8")
    out.write(struct.pack(">H", len(b)))
    out.write(b)


def _w_payload(out, t, v):
    if t == BYTE:
        out.write(struct.pack(">b", int(v)))
    elif t == SHORT:
        out.write(struct.pack(">h", v))
    elif t == INT:
        out.write(struct.pack(">i", v))
    elif t == LONG:
        out.write(struct.pack(">q", v))
    elif t == FLOAT:
        out.write(struct.pack(">f", v))
    elif t == DOUBLE:
        out.write(struct.pack(">d", v))
    elif t == STRING:
        _w_string(out, v)
    elif t == BYTE_ARRAY:
        out.write(struct.pack(">i", len(v)))
        out.write(struct.pack(f">{len(v)}b", *v))
    elif t == INT_ARRAY:
        out.write(struct.pack(">i", len(v)))
        out.write(struct.pack(f">{len(v)}i", *v))
    elif t == LONG_ARRAY:
        out.write(struct.pack(">i", len(v)))
        out.write(struct.pack(f">{len(v)}q", *v))
    elif t == LIST:
        kind = getattr(v, "kind", None)
        if kind is None:
            kind = tag_id(v[0]) if v else END
        out.write(struct.pack(">bi", kind, len(v)))
        for x in v:
            _w_payload(out, kind, x)
    elif t == COMPOUND:
        for k, x in v.items():
            xt = tag_id(x)
            out.write(struct.pack(">b", xt))
            _w_string(out, k)
            _w_payload(out, xt, x)
        out.write(b"\x00")
    else:
        raise ValueError(t)


def dumps(root, compress=True):
    out = io.BytesIO()
    out.write(b"\x0a")
    _w_string(out, "")
    _w_payload(out, COMPOUND, root)
    data = out.getvalue()
    return gzip.compress(data, mtime=0) if compress else data


class _R:
    def __init__(self, b):
        self.b, self.p = b, 0

    def take(self, fmt):
        v = struct.unpack_from(fmt, self.b, self.p)
        self.p += struct.calcsize(fmt)
        return v[0] if len(v) == 1 else v

    def string(self):
        n = self.take(">H")
        s = self.b[self.p:self.p + n].decode("utf-8", errors="replace")
        self.p += n
        return s

    def payload(self, t):
        if t == BYTE:
            return Byte(self.take(">b"))
        if t == SHORT:
            return Short(self.take(">h"))
        if t == INT:
            return Int(self.take(">i"))
        if t == LONG:
            return Long(self.take(">q"))
        if t == FLOAT:
            return Float(self.take(">f"))
        if t == DOUBLE:
            return Double(self.take(">d"))
        if t == STRING:
            return self.string()
        if t in (BYTE_ARRAY, INT_ARRAY, LONG_ARRAY):
            n = self.take(">i")
            code, cls = {BYTE_ARRAY: ("b", ByteArray), INT_ARRAY: ("i", IntArray), LONG_ARRAY: ("q", LongArray)}[t]
            vals = struct.unpack_from(f">{n}{code}", self.b, self.p) if n else ()
            self.p += n * struct.calcsize(code)
            return cls(vals)
        if t == LIST:
            kind, n = self.take(">bi")
            return List([self.payload(kind) for _ in range(n)], kind)
        if t == COMPOUND:
            out = {}
            while True:
                xt = self.take(">b")
                if xt == END:
                    return out
                k = self.string()
                out[k] = self.payload(xt)
        raise ValueError(f"unknown tag {t} at {self.p}")


def loads(data):
    """Parse NBT (gzip or raw) and return the root compound."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    r = _R(data)
    if r.take(">b") != COMPOUND:
        raise ValueError("root is not a compound")
    r.string()
    return r.payload(COMPOUND)


def read(path):
    with open(path, "rb") as f:
        return loads(f.read())


def write(path, root):
    with open(path, "wb") as f:
        f.write(dumps(root))


# ------------------------------------------------------------------ SNBT
_BARE = re.compile(r"[A-Za-z0-9_\-.+]+")
_NUM = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)([bBsSlLfFdD]?)$")


def to_snbt(v, indent=0, step="  "):
    """Format a value as SNBT, multi-line for compounds and lists of compounds."""
    pad, inner = step * indent, step * (indent + 1)
    t = tag_id(v)
    if t == BYTE:
        return f"{int(v)}b"
    if t == SHORT:
        return f"{int(v)}s"
    if t == INT:
        return str(int(v))
    if t == LONG:
        return f"{int(v)}L"
    if t == FLOAT:
        return f"{float(v)!r}f"
    if t == DOUBLE:
        return f"{float(v)!r}d"
    if t == STRING:
        return _quote(v)
    if t in (BYTE_ARRAY, INT_ARRAY, LONG_ARRAY):
        prefix, suffix = {BYTE_ARRAY: ("B", "b"), INT_ARRAY: ("I", ""), LONG_ARRAY: ("L", "L")}[t]
        return f"[{prefix};" + ",".join(f"{int(x)}{suffix}" for x in v) + "]"
    if t == LIST:
        if not v:
            return "[]"
        if all(isinstance(x, (dict, list)) for x in v):
            return "[\n" + ",\n".join(inner + to_snbt(x, indent + 1, step) for x in v) + "\n" + pad + "]"
        return "[" + ",".join(to_snbt(x, indent + 1, step) for x in v) + "]"
    if not v:
        return "{}"
    items = [inner + (k if _BARE.fullmatch(k) else _quote(k)) + ":" + to_snbt(x, indent + 1, step) for k, x in v.items()]
    return "{\n" + ",\n".join(items) + "\n" + pad + "}"


def _quote(s):
    q = "'" if '"' in s and "'" not in s else '"'
    return q + s.replace("\\", "\\\\").replace(q, "\\" + q) + q


class _P:
    def __init__(self, s):
        self.s, self.i = s, 0

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1

    def peek(self):
        self.ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def expect(self, c):
        if self.peek() != c:
            raise ValueError(f"expected {c!r} at {self.i}: {self.s[self.i:self.i + 40]!r}")
        self.i += 1

    def value(self):
        c = self.peek()
        if c == "{":
            self.i += 1
            out = {}
            if self.peek() == "}":
                self.i += 1
                return out
            while True:
                k = self.key()
                self.expect(":")
                out[k] = self.value()
                c = self.peek()
                self.i += 1
                if c == "}":
                    return out
                if c != ",":
                    raise ValueError(f"expected , or }} at {self.i}")
        if c == "[":
            self.i += 1
            if self.s[self.i:self.i + 2] in ("B;", "I;", "L;"):
                kind = self.s[self.i]
                self.i += 2
                vals = []
                while self.peek() != "]":
                    vals.append(int(self.scalar_text().rstrip("bBlL")))
                    if self.peek() == ",":
                        self.i += 1
                self.i += 1
                return {"B": ByteArray, "I": IntArray, "L": LongArray}[kind](vals)
            out = List()
            if self.peek() == "]":
                self.i += 1
                return out
            while True:
                out.append(self.value())
                c = self.peek()
                self.i += 1
                if c == "]":
                    return out
                if c != ",":
                    raise ValueError(f"expected , or ] at {self.i}")
        if c in "\"'":
            return self.quoted()
        return self.scalar(self.scalar_text())

    def key(self):
        c = self.peek()
        if c in "\"'":
            return self.quoted()
        return self.scalar_text()

    def quoted(self):
        q = self.s[self.i]
        self.i += 1
        out = []
        while True:
            c = self.s[self.i]
            self.i += 1
            if c == "\\":
                out.append(self.s[self.i])
                self.i += 1
            elif c == q:
                return "".join(out)
            else:
                out.append(c)

    def scalar_text(self):
        self.ws()
        j = self.i
        while self.i < len(self.s) and self.s[self.i] not in ",:]}[{ \t\r\n":
            self.i += 1
        return self.s[j:self.i]

    @staticmethod
    def scalar(t):
        if t in ("true", "false"):
            return Byte(1 if t == "true" else 0)
        m = _NUM.match(t)
        if m:
            num, suf = m.group(1), m.group(2).lower()
            if suf == "b":
                return Byte(int(num))
            if suf == "s":
                return Short(int(num))
            if suf == "l":
                return Long(int(num))
            if suf == "f":
                return Float(float(num))
            if suf == "d":
                return Double(float(num))
            return Double(float(num)) if any(ch in num for ch in ".eE") else Int(int(num))
        return t


def from_snbt(text):
    p = _P(text)
    v = p.value()
    if p.peek():
        raise ValueError(f"trailing text at {p.i}")
    return v
