"""Small, exact RFC 9162 SHA-256 transparency-tree primitives.

The public hashing API accepts *leaf input bytes*.  It never accepts an
already-hashed leaf under the same name, which prevents accidental double
hashing at protocol call sites.  The recursive functions are intentionally
kept as a slow reference implementation.  :class:`RFC9162Frontier` is the
bounded incremental path used by the V4 physical-evidence projection.

RFC 9162 is an Experimental IETF RFC.  These functions implement only its
binary Merkle-tree algorithms; they do not implement Certificate
Transparency, signatures, COSE receipts, or authenticated range queries.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

RFC9162_SHA256 = "RFC9162_SHA256"
RFC9162_HASH_SIZE = 32
RFC9162_MAX_TREE_SIZE = (1 << 63) - 1


class TransparencyLogError(ValueError):
    """Raised when a transparency-tree value is malformed or out of range."""


def _bytes(value: bytes, *, field: str) -> bytes:
    if type(value) is not bytes:
        raise TransparencyLogError(f"{field} must be exact bytes")
    return value


def _hash(value: bytes, *, field: str) -> bytes:
    digest = _bytes(value, field=field)
    if len(digest) != RFC9162_HASH_SIZE:
        raise TransparencyLogError(
            f"{field} must contain exactly {RFC9162_HASH_SIZE} bytes"
        )
    return digest


def _tree_size(value: int, *, field: str, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TransparencyLogError(f"{field} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum or value > RFC9162_MAX_TREE_SIZE:
        raise TransparencyLogError(
            f"{field} must be between {minimum} and {RFC9162_MAX_TREE_SIZE}"
        )
    return value


def _largest_power_of_two_less_than(value: int) -> int:
    if value <= 1:
        raise TransparencyLogError("tree split requires at least two leaves")
    return 1 << ((value - 1).bit_length() - 1)


def rfc9162_empty_root() -> bytes:
    """Return ``SHA256(b'')``, the RFC 9162 empty-tree hash."""

    return hashlib.sha256(b"").digest()


def rfc9162_leaf_hash(leaf_input: bytes) -> bytes:
    """Hash one application leaf input using the RFC leaf prefix."""

    return hashlib.sha256(b"\x00" + _bytes(leaf_input, field="leaf_input")).digest()


def rfc9162_node_hash(left: bytes, right: bytes) -> bytes:
    """Hash two child hashes using the RFC interior-node prefix."""

    return hashlib.sha256(
        b"\x01" + _hash(left, field="left_hash") + _hash(right, field="right_hash")
    ).digest()


def _root_from_leaf_hash_range(
    leaf_hashes: Sequence[bytes], start: int, end: int
) -> bytes:
    count = end - start
    if count == 0:
        return rfc9162_empty_root()
    if count == 1:
        return _hash(leaf_hashes[start], field="leaf_hash")
    split = _largest_power_of_two_less_than(count)
    return rfc9162_node_hash(
        _root_from_leaf_hash_range(leaf_hashes, start, start + split),
        _root_from_leaf_hash_range(leaf_hashes, start + split, end),
    )


def rfc9162_root_from_leaf_hashes(leaf_hashes: Sequence[bytes]) -> bytes:
    """Return the tree root for values that are already RFC leaf hashes.

    This deliberately distinct API is used by verifiers and storage code.
    Application callers should normally use :func:`rfc9162_tree_hash`.
    """

    if isinstance(leaf_hashes, (bytes, bytearray, memoryview)) or not isinstance(
        leaf_hashes, Sequence
    ):
        raise TransparencyLogError("leaf_hashes must be a sequence")
    checked = tuple(_hash(value, field="leaf_hash") for value in leaf_hashes)
    _tree_size(len(checked), field="tree_size")
    return _root_from_leaf_hash_range(checked, 0, len(checked))


def rfc9162_tree_hash(leaf_inputs: Sequence[bytes]) -> bytes:
    """Return the exact RFC 9162 Merkle Tree Hash for ordered leaf inputs."""

    if isinstance(leaf_inputs, (bytes, bytearray, memoryview)) or not isinstance(
        leaf_inputs, Sequence
    ):
        raise TransparencyLogError("leaf_inputs must be a sequence")
    leaves = tuple(rfc9162_leaf_hash(value) for value in leaf_inputs)
    return _root_from_leaf_hash_range(leaves, 0, len(leaves))


def _subtree_root(leaf_hashes: Sequence[bytes], start: int, count: int) -> bytes:
    return _root_from_leaf_hash_range(leaf_hashes, start, start + count)


def rfc9162_inclusion_proof(
    leaf_inputs: Sequence[bytes], leaf_index: int
) -> tuple[bytes, ...]:
    """Generate the RFC 9162 inclusion path for one leaf."""

    if isinstance(leaf_inputs, (bytes, bytearray, memoryview)) or not isinstance(
        leaf_inputs, Sequence
    ):
        raise TransparencyLogError("leaf_inputs must be a sequence")
    leaves = tuple(rfc9162_leaf_hash(value) for value in leaf_inputs)
    size = _tree_size(len(leaves), field="tree_size", allow_zero=False)
    if isinstance(leaf_index, bool) or not isinstance(leaf_index, int):
        raise TransparencyLogError("leaf_index must be an integer")
    if leaf_index < 0 or leaf_index >= size:
        raise TransparencyLogError("leaf_index is outside the tree")

    def path(index: int, start: int, count: int) -> tuple[bytes, ...]:
        if count == 1:
            return ()
        split = _largest_power_of_two_less_than(count)
        if index < split:
            return path(index, start, split) + (
                _subtree_root(leaves, start + split, count - split),
            )
        return path(index - split, start + split, count - split) + (
            _subtree_root(leaves, start, split),
        )

    return path(leaf_index, 0, size)


def verify_rfc9162_inclusion(
    *,
    leaf_input: bytes,
    leaf_index: int,
    tree_size: int,
    root_hash: bytes,
    inclusion_path: Sequence[bytes],
) -> bool:
    """Verify an RFC 9162 inclusion path, rejecting surplus path nodes."""

    try:
        size = _tree_size(tree_size, field="tree_size", allow_zero=False)
        if isinstance(leaf_index, bool) or not isinstance(leaf_index, int):
            return False
        if leaf_index < 0 or leaf_index >= size:
            return False
        root = _hash(root_hash, field="root_hash")
        if isinstance(inclusion_path, (bytes, bytearray, memoryview)) or not isinstance(
            inclusion_path, Sequence
        ):
            return False
        proof = tuple(_hash(value, field="inclusion_path") for value in inclusion_path)
        fn = leaf_index
        sn = size - 1
        result = rfc9162_leaf_hash(leaf_input)
        for sibling in proof:
            if sn == 0:
                return False
            if fn & 1 or fn == sn:
                result = rfc9162_node_hash(sibling, result)
                if not fn & 1:
                    while fn != 0 and not fn & 1:
                        fn >>= 1
                        sn >>= 1
            else:
                result = rfc9162_node_hash(result, sibling)
            fn >>= 1
            sn >>= 1
        return sn == 0 and result == root
    except (TransparencyLogError, TypeError):
        return False


def rfc9162_consistency_proof(
    leaf_inputs: Sequence[bytes], first_tree_size: int
) -> tuple[bytes, ...]:
    """Generate a minimal consistency proof for a prefix tree.

    The project wrapper defines empty proofs for an empty prefix and for equal
    tree sizes.  RFC 9162's recursive algorithm handles ``0 < first < second``.
    """

    if isinstance(leaf_inputs, (bytes, bytearray, memoryview)) or not isinstance(
        leaf_inputs, Sequence
    ):
        raise TransparencyLogError("leaf_inputs must be a sequence")
    leaves = tuple(rfc9162_leaf_hash(value) for value in leaf_inputs)
    second = _tree_size(len(leaves), field="second_tree_size")
    first = _tree_size(first_tree_size, field="first_tree_size")
    if first > second:
        raise TransparencyLogError("first_tree_size exceeds second_tree_size")
    if first in {0, second}:
        return ()

    def subproof(
        prefix_count: int,
        start: int,
        count: int,
        prefix_root_known: bool,
    ) -> tuple[bytes, ...]:
        if prefix_count == count:
            if prefix_root_known:
                return ()
            return (_subtree_root(leaves, start, count),)
        split = _largest_power_of_two_less_than(count)
        if prefix_count <= split:
            return subproof(prefix_count, start, split, prefix_root_known) + (
                _subtree_root(leaves, start + split, count - split),
            )
        return subproof(
            prefix_count - split,
            start + split,
            count - split,
            False,
        ) + (_subtree_root(leaves, start, split),)

    return subproof(first, 0, second, True)


def verify_rfc9162_consistency(
    *,
    first_tree_size: int,
    second_tree_size: int,
    first_root_hash: bytes,
    second_root_hash: bytes,
    consistency_path: Sequence[bytes],
) -> bool:
    """Verify append-only consistency between two RFC 9162 tree heads."""

    try:
        first = _tree_size(first_tree_size, field="first_tree_size")
        second = _tree_size(second_tree_size, field="second_tree_size")
        first_root = _hash(first_root_hash, field="first_root_hash")
        second_root = _hash(second_root_hash, field="second_root_hash")
        if isinstance(
            consistency_path, (bytes, bytearray, memoryview)
        ) or not isinstance(consistency_path, Sequence):
            return False
        proof = tuple(
            _hash(value, field="consistency_path") for value in consistency_path
        )
        if first > second:
            return False
        if first == second:
            return (
                not proof
                and first_root == second_root
                and (first != 0 or first_root == rfc9162_empty_root())
            )
        if first == 0:
            return not proof and first_root == rfc9162_empty_root()
        if not proof:
            return False

        work = proof
        if first & (first - 1) == 0:
            work = (first_root,) + work

        fn = first - 1
        sn = second - 1
        if fn & 1:
            while fn & 1:
                fn >>= 1
                sn >>= 1

        first_result = work[0]
        second_result = work[0]
        for component in work[1:]:
            if sn == 0:
                return False
            if fn & 1 or fn == sn:
                first_result = rfc9162_node_hash(component, first_result)
                second_result = rfc9162_node_hash(component, second_result)
                if not fn & 1:
                    while fn != 0 and not fn & 1:
                        fn >>= 1
                        sn >>= 1
            else:
                second_result = rfc9162_node_hash(second_result, component)
            fn >>= 1
            sn >>= 1
        return sn == 0 and first_result == first_root and second_result == second_root
    except (TransparencyLogError, TypeError):
        return False


@dataclass(frozen=True, slots=True)
class RFC9162StoredHash:
    """One finalized RFC tree node addressed by level and subtree index."""

    level: int
    subtree_index: int
    value: bytes

    def __post_init__(self) -> None:
        if isinstance(self.level, bool) or not isinstance(self.level, int):
            raise TransparencyLogError("stored-hash level must be an integer")
        if self.level < 0 or self.level > 62:
            raise TransparencyLogError("stored-hash level is out of range")
        if isinstance(self.subtree_index, bool) or not isinstance(
            self.subtree_index, int
        ):
            raise TransparencyLogError("stored-hash subtree_index must be an integer")
        if self.subtree_index < 0 or self.subtree_index > RFC9162_MAX_TREE_SIZE:
            raise TransparencyLogError("stored-hash subtree_index is out of range")
        object.__setattr__(self, "value", _hash(self.value, field="stored_hash"))


@dataclass(frozen=True, slots=True)
class RFC9162Frontier:
    """Bounded incremental state for one continuous RFC 9162 tree.

    ``peaks`` are ordered left-to-right and their levels are the set bits of
    ``tree_size`` in descending order.  At this generic implementation's
    maximum size the object contains no more than 63 hashes; application
    profiles may impose a smaller bound.
    """

    tree_size: int = 0
    peaks: tuple[tuple[int, bytes], ...] = ()

    def __post_init__(self) -> None:
        size = _tree_size(self.tree_size, field="tree_size")
        if not isinstance(self.peaks, tuple):
            raise TransparencyLogError("peaks must be a tuple")
        expected_levels = tuple(
            level
            for level in range(size.bit_length() - 1, -1, -1)
            if size & (1 << level)
        )
        normalized: list[tuple[int, bytes]] = []
        for item in self.peaks:
            if not isinstance(item, tuple) or len(item) != 2:
                raise TransparencyLogError("each peak must be a (level, hash) tuple")
            level, value = item
            if isinstance(level, bool) or not isinstance(level, int):
                raise TransparencyLogError("peak level must be an integer")
            normalized.append((level, _hash(value, field="peak_hash")))
        if tuple(level for level, _ in normalized) != expected_levels:
            raise TransparencyLogError("peak levels do not match tree_size")
        object.__setattr__(self, "tree_size", size)
        object.__setattr__(self, "peaks", tuple(normalized))

    @property
    def root_hash(self) -> bytes:
        if not self.peaks:
            return rfc9162_empty_root()
        result = self.peaks[-1][1]
        for _, left in reversed(self.peaks[:-1]):
            result = rfc9162_node_hash(left, result)
        return result

    def append_leaf_input(
        self, leaf_input: bytes
    ) -> tuple[RFC9162Frontier, tuple[RFC9162StoredHash, ...]]:
        """Append one leaf and return the new frontier plus finalized hashes."""

        if self.tree_size >= RFC9162_MAX_TREE_SIZE:
            raise TransparencyLogError("tree has reached the RFC implementation limit")
        leaf = rfc9162_leaf_hash(leaf_input)
        index = self.tree_size
        level = 0
        carry = leaf
        peaks = list(self.peaks)
        stored = [RFC9162StoredHash(level=0, subtree_index=index, value=leaf)]
        merge_bits = index
        while merge_bits & 1:
            if not peaks or peaks[-1][0] != level:
                raise TransparencyLogError("frontier is inconsistent during append")
            _, left = peaks.pop()
            carry = rfc9162_node_hash(left, carry)
            level += 1
            stored.append(
                RFC9162StoredHash(
                    level=level,
                    subtree_index=index >> level,
                    value=carry,
                )
            )
            merge_bits >>= 1
        peaks.append((level, carry))
        return RFC9162Frontier(self.tree_size + 1, tuple(peaks)), tuple(stored)

    def append_many(
        self, leaf_inputs: Iterable[bytes]
    ) -> tuple[RFC9162Frontier, tuple[RFC9162StoredHash, ...]]:
        """Append ordered inputs without making batch boundaries semantic."""

        frontier = self
        stored: list[RFC9162StoredHash] = []
        for leaf_input in leaf_inputs:
            frontier, created = frontier.append_leaf_input(leaf_input)
            stored.extend(created)
        return frontier, tuple(stored)


def rfc9162_root_from_stored_hashes(
    tree_size: int,
    reader: Callable[[int, int], bytes],
) -> bytes:
    """Reconstruct a tree head from finalized-subtree coordinate lookups."""

    size = _tree_size(tree_size, field="tree_size")
    if not callable(reader):
        raise TransparencyLogError("reader must be callable")
    if size == 0:
        return rfc9162_empty_root()
    peaks: list[bytes] = []
    cursor = 0
    for level in range(size.bit_length() - 1, -1, -1):
        width = 1 << level
        if size & width:
            peaks.append(_hash(reader(level, cursor >> level), field="stored_hash"))
            cursor += width
    result = peaks[-1]
    for left in reversed(peaks[:-1]):
        result = rfc9162_node_hash(left, result)
    return result


__all__ = [
    "RFC9162_HASH_SIZE",
    "RFC9162_MAX_TREE_SIZE",
    "RFC9162_SHA256",
    "RFC9162Frontier",
    "RFC9162StoredHash",
    "TransparencyLogError",
    "rfc9162_consistency_proof",
    "rfc9162_empty_root",
    "rfc9162_inclusion_proof",
    "rfc9162_leaf_hash",
    "rfc9162_node_hash",
    "rfc9162_root_from_leaf_hashes",
    "rfc9162_root_from_stored_hashes",
    "rfc9162_tree_hash",
    "verify_rfc9162_consistency",
    "verify_rfc9162_inclusion",
]
