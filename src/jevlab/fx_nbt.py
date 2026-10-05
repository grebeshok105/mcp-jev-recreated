"""Minimal Minecraft Java NBT reader/writer for Photon .fx files.

.fx is `NbtIo.readCompressed` output: gzip-wrapped standard NBT with a
named root compound (`fxData`). This module intentionally preserves
UNKNOWN tags verbatim: decode keeps tag types + order, encode writes
them back untouched, so a no-op round-trip is byte-faithful except for
gzip header noise.
"""
from __future__ import annotations

import gzip
import os
import struct
from dataclasses import dataclass, field
from typing import Any

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

_SCALAR_FMT = {
    TAG_BYTE: ">b",
    TAG_SHORT: ">h",
    TAG_INT: ">i",
    TAG_LONG: ">q",
    TAG_FLOAT: ">f",
    TAG_DOUBLE: ">d",
}


@dataclass
class Tag:
    """A typed NBT value. `value` for compound = list[(name, Tag)] (ordered).

    `elem_type` is meaningful only for TAG_LIST: Java stores the declared
    element type even when the list is empty. Keeping it preserves the
    byte shape of empty non-END lists; -1 = infer from elements (END when
    empty, matching Photon output).
    """
    type: int
    value: Any = None
    elem_type: int = -1

    def get(self, name: str) -> "Tag | None":
        if self.type != TAG_COMPOUND:
            raise TypeError("not a compound")
        for n, t in self.value:
            if n == name:
                return t
        return None

    def set(self, name: str, tag: "Tag") -> None:
        items = self.value
        for i, (n, _) in enumerate(items):
            if n == name:
                items[i] = (n, tag)
                return
        items.append((name, tag))

    def keys(self) -> list[str]:
        return [n for n, _ in self.value]


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def _take(self, n: int) -> bytes:
        b = self.data[self.pos:self.pos + n]
        if len(b) != n:
            raise ValueError("unexpected end of NBT data")
        self.pos += n
        return b

    def _read(self, fmt: str):
        return struct.unpack(fmt, self._take(struct.calcsize(fmt)))[0]

    def read_u8(self) -> int:
        return self._take(1)[0]

    def read_i16(self) -> int:
        return self._read(">h")

    def read_i32(self) -> int:
        return self._read(">i")

    def read_str(self) -> str:
        n = self._read(">H")
        # strict: MUTF-8 forms Java writes (overlong NUL, surrogate pairs)
        # raise here instead of silently mangling — a decode that differs
        # from Java's should be loud, not corrupt.
        return self._take(n).decode("utf-8")

    def payload(self, t: int) -> Tag:
        if t in _SCALAR_FMT:
            return Tag(t, self._read(_SCALAR_FMT[t]))
        if t == TAG_STRING:
            return Tag(t, self.read_str())
        if t == TAG_BYTE_ARRAY:
            n = self.read_i32()
            return Tag(t, self._take(n))
        if t == TAG_INT_ARRAY:
            n = self.read_i32()
            return Tag(t, [self._read(">i") for _ in range(n)])
        if t == TAG_LONG_ARRAY:
            n = self.read_i32()
            return Tag(t, [self._read(">q") for _ in range(n)])
        if t == TAG_LIST:
            et = self.read_u8()
            n = self.read_i32()
            return Tag(t, [self.payload(et) for _ in range(n)], et)
        if t == TAG_COMPOUND:
            items: list[tuple[str, Tag]] = []
            while True:
                nt = self.read_u8()
                if nt == TAG_END:
                    break
                name = self.read_str()
                items.append((name, self.payload(nt)))
            return Tag(t, items)
        raise ValueError(f"unknown tag type {t}")

    def root(self) -> tuple[str, Tag]:
        t = self.read_u8()
        if t != TAG_COMPOUND:
            raise ValueError(f"root must be compound, got {t}")
        name = self.read_str()
        return name, self.payload(TAG_COMPOUND)


def _enc_str(s: str) -> bytes:
    if "\x00" in s or any(ord(c) > 0xFFFF for c in s):
        # Java writeUTF is modified UTF-8 (NUL and non-BMP encode
        # differently); we cannot represent it faithfully — refuse.
        raise ValueError("string not encodable as strict UTF-8 "
                         "(NUL/non-BMP chars need MUTF-8)")
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b


def _enc_payload(tag: Tag) -> bytes:
    t = tag.type
    if t in _SCALAR_FMT:
        return struct.pack(_SCALAR_FMT[t], tag.value)
    if t == TAG_STRING:
        return _enc_str(tag.value)
    if t == TAG_BYTE_ARRAY:
        return struct.pack(">i", len(tag.value)) + bytes(tag.value)
    if t == TAG_INT_ARRAY:
        return struct.pack(">i", len(tag.value)) + b"".join(
            struct.pack(">i", v) for v in tag.value)
    if t == TAG_LONG_ARRAY:
        return struct.pack(">i", len(tag.value)) + b"".join(
            struct.pack(">q", v) for v in tag.value)
    if t == TAG_LIST:
        et = tag.elem_type
        if et < 0:
            et = tag.value[0].type if tag.value else TAG_END
        return (struct.pack(">Bi", et, len(tag.value)) +
                b"".join(_enc_payload(v) for v in tag.value))
    if t == TAG_COMPOUND:
        out = []
        for name, sub in tag.value:
            out.append(struct.pack(">B", sub.type) + _enc_str(name) +
                       _enc_payload(sub))
        out.append(b"\x00")
        return b"".join(out)
    raise ValueError(f"unknown tag type {t}")


def loads(data: bytes) -> tuple[str, Tag]:
    r = Reader(data)
    return r.root()


def dumps(name: str, root: Tag) -> bytes:
    return struct.pack(">B", TAG_COMPOUND) + _enc_str(name) + _enc_payload(root)


def load_fx(path: str) -> tuple[str, Tag]:
    with gzip.open(path, "rb") as f:
        return loads(f.read())


def save_fx(path: str, name: str, root: Tag) -> None:
    # serialize fully BEFORE truncating the target (encode errors must
    # leave the old file intact), then atomically rename into place.
    raw = gzip.compress(dumps(name, root))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)
