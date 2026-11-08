import inspect
from pathlib import Path

import pytest

from pyct.config.command_line import UsageError
from pyct.run.seeds_file import FileSeed, SeedsFile, checked_seeds, distinct, read_seeds_file
from pyct.run.target import Target


def name_and_age(name: str, age: int) -> str:
    return f"{name}{age}"


def anything(x: object) -> object:
    return x


def target_for(fn: object) -> Target:
    assert callable(fn)
    return Target(spec="m::f", fn=fn, file="m.py", signature=inspect.signature(fn))


def written(folder: Path, data: bytes) -> str:
    path = folder / "seeds.jsonl"
    path.write_bytes(data)
    return str(path)


def test_read_keeps_each_line_that_is_not_blank_with_its_number(tmp_path: Path) -> None:
    name = written(tmp_path, b'{"x": 1}\r\n \t\r\n\r{"x": 2}')

    assert read_seeds_file(name) == SeedsFile(name, ((1, '{"x": 1}'), (4, '{"x": 2}')))


def test_read_keeps_a_line_separator_inside_a_string_in_its_line(tmp_path: Path) -> None:
    name = written(tmp_path, '{"x": "a\u2028b"}\n'.encode())

    assert read_seeds_file(name).lines == ((1, '{"x": "a\u2028b"}'),)


def test_read_refuses_a_file_that_is_not_utf_8(tmp_path: Path) -> None:
    name = written(tmp_path, b'{"x": "\xff"}\n')

    with pytest.raises(UsageError, match=f"^cannot read {name}: 'utf-8' codec can't decode"):
        read_seeds_file(name)


def test_read_refuses_a_folder(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match=f"^cannot read {tmp_path}: "):
        read_seeds_file(str(tmp_path))


def test_checked_writes_each_reason_of_a_line_on_its_own_line() -> None:
    file = SeedsFile("s.jsonl", ((1, '{"name": "a", "age": 1}'), (2, '{"name": 5, "age": "x"}')))

    with pytest.raises(UsageError) as raised:
        checked_seeds(target_for(name_and_age), file)

    assert str(raised.value).splitlines() == [
        "s.jsonl:2: name must be a str, got 5",
        's.jsonl:2: age must be an int, got "x"',
    ]


def test_checked_gives_each_seed_with_its_line() -> None:
    file = SeedsFile("s.jsonl", ((1, '{"x": 1}'), (3, '{"x": 2}')))

    assert checked_seeds(target_for(anything), file) == (
        FileSeed({"x": 1}, "s.jsonl", 1),
        FileSeed({"x": 2}, "s.jsonl", 3),
    )


def test_distinct_leaves_out_a_seed_an_earlier_line_gave() -> None:
    seeds = [FileSeed({"x": 1}, "s", 1), FileSeed({"x": 2}, "s", 2), FileSeed({"x": 1}, "s", 4)]

    kept, skipped = distinct(seeds)

    assert kept == tuple(seeds[:2])
    assert skipped == ("skipped s:4, same seed as line 1",)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ({"x": 1}, {"x": 1.0}),
        ({"x": 1}, {"x": True}),
        ({"x": 0.0}, {"x": -0.0}),
        ({"x": 1, "y": 2}, {"y": 2, "x": 1}),
    ],
)
def test_distinct_keeps_seeds_that_write_other_json(
    first: dict[str, object], second: dict[str, object]
) -> None:
    seeds = [FileSeed(first, "s", 1), FileSeed(second, "s", 2)]

    assert distinct(seeds) == (tuple(seeds), ())


def test_distinct_counts_two_nans_as_the_same_seed() -> None:
    seeds = [FileSeed({"x": float("nan")}, "s", 1), FileSeed({"x": float("nan")}, "s", 2)]

    assert distinct(seeds)[1] == ("skipped s:2, same seed as line 1",)


def test_read_leaves_a_byte_order_mark_out_of_the_first_line(tmp_path: Path) -> None:
    name = written(tmp_path, b'\xef\xbb\xbf{"x": 1}\n')

    assert read_seeds_file(name).lines == ((1, '{"x": 1}'),)


def test_read_refuses_an_empty_name() -> None:
    with pytest.raises(UsageError, match="^--seeds needs a file name$"):
        read_seeds_file("")


def test_checked_keeps_a_reason_with_a_line_break_on_one_line() -> None:
    file = SeedsFile("s.jsonl", ((1, '{"a\\nb": 5}'),))

    with pytest.raises(UsageError) as raised:
        checked_seeds(target_for(anything), file)

    reason = str(raised.value)
    assert reason.startswith("s.jsonl:1: args (a\nb) do not fit (x): ")
    assert reason.count("s.jsonl:1: ") == 1
