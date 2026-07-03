"""Prefixed ULID identifiers (architecture.md §3: ids are time-sortable ULIDs).

Stdlib implementation of ULID (https://github.com/ulid/spec):
48-bit millisecond timestamp + 80 bits of randomness, Crockford base32.
Lexicographic order of the encoded string matches creation-time order.
"""

import os
import time

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

MEMORY_ID_PREFIX = "mem_"
PROJECT_ID_PREFIX = "proj_"


def _encode_base32(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD32[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def new_ulid() -> str:
    timestamp_ms = time.time_ns() // 1_000_000
    randomness = int.from_bytes(os.urandom(10), "big")
    return _encode_base32(timestamp_ms, 10) + _encode_base32(randomness, 16)


def new_memory_id() -> str:
    return MEMORY_ID_PREFIX + new_ulid()


def new_project_id() -> str:
    return PROJECT_ID_PREFIX + new_ulid()
