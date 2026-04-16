"""Shard selection for parallel baseline generation across workers.

Running baselines for 80+ targets sequentially is slow. The CLI
accepts ``--shard N/K`` so K workers each take a disjoint slice.
Modulo (round-robin) partitioning keeps the per-worker load roughly
even even when a contiguous run of targets is disproportionately
expensive.
"""

from __future__ import annotations

import pytest
from tools.benchmark.baseline_generator import _apply_shard


def test_shard_returns_all_when_unset():
    items = list(range(10))
    assert _apply_shard(items, shard=None) == items


def test_shard_0_of_2_picks_even_indices():
    items = list(range(10))
    assert _apply_shard(items, shard="0/2") == [0, 2, 4, 6, 8]


def test_shard_1_of_2_picks_odd_indices():
    items = list(range(10))
    assert _apply_shard(items, shard="1/2") == [1, 3, 5, 7, 9]


def test_shard_distributes_across_four_workers():
    items = list(range(12))
    partitions = [_apply_shard(items, shard=f"{i}/4") for i in range(4)]
    assert [sorted(p) for p in partitions] == [
        [0, 4, 8],
        [1, 5, 9],
        [2, 6, 10],
        [3, 7, 11],
    ]


def test_shard_unions_back_to_full_set():
    items = list(range(17))
    k = 4
    union = set()
    for i in range(k):
        union.update(_apply_shard(items, shard=f"{i}/{k}"))
    assert union == set(items)


def test_shard_rejects_malformed_spec():
    with pytest.raises(ValueError):
        _apply_shard([1, 2, 3], shard="foo")


def test_shard_rejects_index_out_of_range():
    with pytest.raises(ValueError):
        _apply_shard([1, 2, 3], shard="3/3")  # valid indices are 0..2


def test_shard_rejects_zero_count():
    with pytest.raises(ValueError):
        _apply_shard([1, 2, 3], shard="0/0")
