from __future__ import annotations

import hashlib
import random

import pytest

from riskyieldmm.trading.transparency_log import (
    RFC9162Frontier,
    TransparencyLogError,
    rfc9162_consistency_proof,
    rfc9162_empty_root,
    rfc9162_inclusion_proof,
    rfc9162_leaf_hash,
    rfc9162_node_hash,
    rfc9162_root_from_stored_hashes,
    rfc9162_tree_hash,
    verify_rfc9162_consistency,
    verify_rfc9162_inclusion,
)

GOLDEN_ROOTS = {
    0: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    1: "c67f9ffe68e0761021341dd516428f42fbdea633731cbdada03bea6b84c652f7",
    2: "46c78708413a23175f51faf1c22604bccb44482d553b45943b189130ea8221c8",
    3: "c64c5b9326951a2db82d5462565696286659d1c7a4a26a92703568f63462f7ba",
    4: "8df3870b33fae650e81938994f98eb4551b143b86c95d3dae4e6444e00715016",
    7: "73a590fb266b81557040b146b9d479e2a1b5849b125167642f5b64866f1d5c7d",
    8: "3b0c343929799440e33ea5b8376857850457f497736ca6ada6c320ee235b67a4",
    9: "68be87542fb826407adcdf28d49f0376082c7f3070e51523b21a8e75ddf90fcf",
}


def leaves(count: int) -> list[bytes]:
    return [f"d{index}".encode() for index in range(count)]


def test_rfc9162_hard_coded_roots_and_domain_separation() -> None:
    for size, expected in GOLDEN_ROOTS.items():
        assert rfc9162_tree_hash(leaves(size)).hex() == expected

    assert rfc9162_empty_root() == hashlib.sha256(b"").digest()
    assert rfc9162_leaf_hash(b"d0") == hashlib.sha256(b"\x00d0").digest()
    left = rfc9162_leaf_hash(b"d0")
    right = rfc9162_leaf_hash(b"d1")
    assert (
        rfc9162_node_hash(left, right)
        == hashlib.sha256(b"\x01" + left + right).digest()
    )
    assert rfc9162_leaf_hash(left) != left


@pytest.mark.parametrize("size", [0, 1, 2, 3, 4, 7, 8, 9, 4095, 4096, 4097])
def test_incremental_frontier_and_stored_hashes_match_slow_tree(size: int) -> None:
    frontier = RFC9162Frontier()
    stored: dict[tuple[int, int], bytes] = {}
    for value in leaves(size):
        frontier, created = frontier.append_leaf_input(value)
        for item in created:
            key = (item.level, item.subtree_index)
            assert key not in stored
            stored[key] = item.value

    expected = rfc9162_tree_hash(leaves(size))
    assert frontier.tree_size == size
    assert frontier.root_hash == expected
    assert len(frontier.peaks) == size.bit_count()
    assert (
        rfc9162_root_from_stored_hashes(
            size, lambda level, index: stored[(level, index)]
        )
        == expected
    )


def test_frontier_is_batch_invariant() -> None:
    values = leaves(4097)
    expected = rfc9162_tree_hash(values)
    final_states = []
    for batch_size in (1, 17, 256):
        frontier = RFC9162Frontier()
        stored: dict[tuple[int, int], bytes] = {}
        for start in range(0, len(values), batch_size):
            frontier, created = frontier.append_many(values[start : start + batch_size])
            for item in created:
                stored[(item.level, item.subtree_index)] = item.value
        final_states.append((frontier.tree_size, frontier.root_hash, stored))
        assert frontier.root_hash == expected
    assert final_states[0] == final_states[1] == final_states[2]


@pytest.mark.parametrize("size", [1, 2, 3, 4, 7, 8, 9, 31, 32, 33])
def test_every_small_inclusion_proof_verifies(size: int) -> None:
    values = leaves(size)
    root = rfc9162_tree_hash(values)
    for index, value in enumerate(values):
        proof = rfc9162_inclusion_proof(values, index)
        assert verify_rfc9162_inclusion(
            leaf_input=value,
            leaf_index=index,
            tree_size=size,
            root_hash=root,
            inclusion_path=proof,
        )


def test_inclusion_proof_tampering_and_shape_fail_closed() -> None:
    values = leaves(9)
    root = rfc9162_tree_hash(values)
    proof = rfc9162_inclusion_proof(values, 8)
    changed = bytes([proof[0][0] ^ 1]) + proof[0][1:]

    kwargs = {
        "leaf_input": values[8],
        "leaf_index": 8,
        "tree_size": len(values),
        "root_hash": root,
    }
    assert not verify_rfc9162_inclusion(**kwargs, inclusion_path=(changed, *proof[1:]))
    assert not verify_rfc9162_inclusion(**kwargs, inclusion_path=proof[:-1])
    assert not verify_rfc9162_inclusion(**kwargs, inclusion_path=(*proof, b"x" * 32))
    assert not verify_rfc9162_inclusion(
        **{**kwargs, "leaf_index": 9}, inclusion_path=proof
    )
    assert not verify_rfc9162_inclusion(
        **{**kwargs, "tree_size": 8}, inclusion_path=proof
    )
    assert not verify_rfc9162_inclusion(
        **{**kwargs, "root_hash": b"x" * 31}, inclusion_path=proof
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [(0, 1), (1, 2), (1, 3), (2, 3), (3, 4), (3, 7), (4, 7), (6, 7)],
)
def test_consistency_vectors_verify(first: int, second: int) -> None:
    values = leaves(second)
    proof = rfc9162_consistency_proof(values, first)
    assert verify_rfc9162_consistency(
        first_tree_size=first,
        second_tree_size=second,
        first_root_hash=rfc9162_tree_hash(values[:first]),
        second_root_hash=rfc9162_tree_hash(values),
        consistency_path=proof,
    )


def test_consistency_proof_tampering_and_wrapper_edges_fail_closed() -> None:
    values = leaves(7)
    first_root = rfc9162_tree_hash(values[:3])
    second_root = rfc9162_tree_hash(values)
    proof = rfc9162_consistency_proof(values, 3)
    changed = bytes([proof[0][0] ^ 1]) + proof[0][1:]
    kwargs = {
        "first_tree_size": 3,
        "second_tree_size": 7,
        "first_root_hash": first_root,
        "second_root_hash": second_root,
    }
    assert not verify_rfc9162_consistency(
        **kwargs, consistency_path=(changed, *proof[1:])
    )
    assert not verify_rfc9162_consistency(**kwargs, consistency_path=proof[:-1])
    assert not verify_rfc9162_consistency(
        **kwargs, consistency_path=(*proof, b"x" * 32)
    )
    assert verify_rfc9162_consistency(
        first_tree_size=0,
        second_tree_size=7,
        first_root_hash=rfc9162_empty_root(),
        second_root_hash=second_root,
        consistency_path=(),
    )
    assert not verify_rfc9162_consistency(
        first_tree_size=0,
        second_tree_size=7,
        first_root_hash=b"x" * 32,
        second_root_hash=second_root,
        consistency_path=(),
    )
    assert verify_rfc9162_consistency(
        first_tree_size=0,
        second_tree_size=0,
        first_root_hash=rfc9162_empty_root(),
        second_root_hash=rfc9162_empty_root(),
        consistency_path=(),
    )
    assert not verify_rfc9162_consistency(
        first_tree_size=0,
        second_tree_size=0,
        first_root_hash=rfc9162_empty_root(),
        second_root_hash=b"x" * 32,
        consistency_path=(),
    )
    assert verify_rfc9162_consistency(
        first_tree_size=7,
        second_tree_size=7,
        first_root_hash=second_root,
        second_root_hash=second_root,
        consistency_path=(),
    )
    assert not verify_rfc9162_consistency(
        first_tree_size=7,
        second_tree_size=3,
        first_root_hash=second_root,
        second_root_hash=first_root,
        consistency_path=proof,
    )


def test_randomized_slow_incremental_and_proof_differential() -> None:
    generator = random.Random(9162)
    for _ in range(40):
        size = generator.randint(1, 80)
        values = [generator.randbytes(generator.randint(0, 64)) for _ in range(size)]
        frontier = RFC9162Frontier()
        frontier, _ = frontier.append_many(values)
        root = rfc9162_tree_hash(values)
        assert frontier.root_hash == root

        index = generator.randrange(size)
        inclusion = rfc9162_inclusion_proof(values, index)
        assert verify_rfc9162_inclusion(
            leaf_input=values[index],
            leaf_index=index,
            tree_size=size,
            root_hash=root,
            inclusion_path=inclusion,
        )

        first = generator.randrange(size + 1)
        consistency = rfc9162_consistency_proof(values, first)
        assert verify_rfc9162_consistency(
            first_tree_size=first,
            second_tree_size=size,
            first_root_hash=rfc9162_tree_hash(values[:first]),
            second_root_hash=root,
            consistency_path=consistency,
        )


def test_invalid_inputs_are_rejected_without_implicit_coercion() -> None:
    with pytest.raises(TransparencyLogError, match="leaf_inputs must be a sequence"):
        rfc9162_tree_hash(b"not-a-sequence-of-leaves")
    with pytest.raises(TransparencyLogError, match="exact bytes"):
        rfc9162_leaf_hash(bytearray(b"x"))  # type: ignore[arg-type]
    with pytest.raises(TransparencyLogError, match="outside the tree"):
        rfc9162_inclusion_proof([b"x"], 1)
    with pytest.raises(TransparencyLogError, match="exceeds"):
        rfc9162_consistency_proof([b"x"], 2)
    with pytest.raises(TransparencyLogError, match="peak levels"):
        RFC9162Frontier(tree_size=1, peaks=())
