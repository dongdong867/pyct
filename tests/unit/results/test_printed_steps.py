"""What `printed_forks` writes, held byte for byte against what it wrote at 62e9e5cd.

Counting a line's cut parts spends a fixed budget of steps, and the parts the steps run out
on print no count. So which parts carry a count rests on how many steps each list, operand and
run costs, not only on the counts. Each case runs with its default limit and with limits across
the window where the base's steps ran out part way, and the digests hold every count, and every
count left out, to what the base wrote.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from pyct.core.branch import Branch, Expression
from pyct.results.printed import COUNTING_STEPS, printed_forks
from tests.unit.results.test_line_budget import _countdown
from tests.unit.results.test_printed import (
    GATHERED_FROM,
    _edit_loop,
    _gathered,
    _orthogonal_vectors,
)


def _an_access(part: Expression) -> bool:
    """An index into the parameter ``s``, as a seed with a value inside an argument names one."""
    return isinstance(part, list) and part[0] == "[]" and part[1] == "s"


@dataclass(frozen=True)
class _Case:
    """Forks to print, what names a leaf, and the window of limits between the most steps under
    which the base counted no part and the fewest under which it counted every part it counts
    by default."""

    build: Callable[[], list[Branch]]
    is_leaf: Callable[[Expression], bool] | None
    window: tuple[int, int]

    def limits(self) -> tuple[int, ...]:
        """The default, then nine limits across the window, its two ends included."""
        low, high = self.window
        return (COUNTING_STEPS, *(low + (high - low) * k // 8 for k in range(9)))


_CASES = {
    "countdown 2,000": _Case(lambda: _countdown(2_000), None, (12_635, 29_486)),
    "countdown 20,000": _Case(lambda: _countdown(20_000), None, (120_635, 663_212)),
    "edit loop 60": _Case(lambda: _edit_loop(60), None, (1_014, 2_700)),
    "edit loop 120": _Case(lambda: _edit_loop(120), None, (2_178, 5_986)),
    "gathered from s": _Case(lambda: _gathered(300, GATHERED_FROM["s"]), None, (813, 814)),
    "gathered 3,000 from s[1:]": _Case(
        lambda: _gathered(3_000, GATHERED_FROM["s[1:]"]), None, (60_310, 60_311)
    ),
    "gathered 3,000 accesses": _Case(
        lambda: _gathered(3_000, GATHERED_FROM["s"]), _an_access, (20_013, 20_014)
    ),
    "orthogonal vectors": _Case(lambda: _orthogonal_vectors(256, 16, 4), None, (11_906, 90_216)),
}

# each case's digest at each of its limits, as 62e9e5cd wrote them
_WRITTEN: dict[str, tuple[str, ...]] = {
    "countdown 2,000": (
        "7faf00ca9972ce19dad19dfeb2a0742675ac80c26a98689999889998c3f620b2",
        "4721a95578f2ae955d8f44c82d71593109375259e741f8fd0500ec0f587e9d5a",
        "4e36dc084c671c760c14abf0ffc21e3bd721326d08875193b82f1aab157b0fe3",
        "bcaf32edde8990078ba5832ec44e0509244a8fffc0f870192fddcc50a914dec0",
        "97fc854ae09ad085715143ee2e3bbe50a8c84e20c4df4bb261688a7c114146de",
        "57d622241e77c4af9f201f7716c43c714a9ba1c2563d25af199fbf35ba7e6ab0",
        "7c9938d457a12d269e2f2bc04dd98eec692961fb235ca35e9a6cf6f5ba8507e1",
        "8d1d38afbef2cfd2e4b41fae1739c79453220226bf18f9776bcc8b08593bfe3d",
        "47f18022b221dacff37f09e5a4e321f423d7949fde92309e4850c7ae1c26689a",
        "7faf00ca9972ce19dad19dfeb2a0742675ac80c26a98689999889998c3f620b2",
    ),
    "countdown 20,000": (
        "0a2e7112c9422c172415f5fa26af95aed28ab5874ac77c0fee7dc0f650864d71",
        "bb74af8afa2b6c6361c791f0e6d08e7bc423e61093273368a87e9d2096a055c1",
        "f7cd816aa372b528982e759a8a566fceb2eaa6c04b975f41f8db6da8d8d235f0",
        "4b03f1e3d2c6dbb8821dff58a3d7c46ba4796b7fe1643eddde9fe1f36553c8d7",
        "ce6dc3396568e9e688886a3e76bf0f1c971479b9df134d07962549008c89c5ac",
        "2ef1948aeb1dcb405c4e106a05e80f3291e594cce081a7e9fbd24329dc0c75a1",
        "a755b289902d1db7f620b33761c4f560364b3fbbd07373ab0fb1d6199c09f623",
        "1772af212534ae3602ceb9bf5b27a0f2fbe4ac20c0fd4f5ac173d78ed18b2143",
        "12ef369769154a9e5555adb2b74fc6e2ef807dcbbbe9b110c96f23f8d9efb879",
        "0a2e7112c9422c172415f5fa26af95aed28ab5874ac77c0fee7dc0f650864d71",
    ),
    "edit loop 60": (
        "98d5ba2bc50ac37159a82b23a17581c2ea6443da048f3b9041fe511e91739009",
        "3d5ac7de6db5781e10c03e5fd2fb770d3cbc2240f3115e827b991dc8c2acd6b5",
        "7e05cc27c9144d9678fa3806225872a243dfbc61e3c9eb853c4ba8e21a8b2b2f",
        "4b7273911fcc8bdf45c824f024ac79dbbb9bdc3964c591b75885e4c265857c0e",
        "cd589281afa08dce7db5dd61e70c7d9459d0fc7671526aabf5bb6ca545576111",
        "234d609961ed5e991e6be750fd45358de72e424cdb7854e29dd45545a18c73f6",
        "3defb1376e058cca4575715a1545dde23415f0ca54c40c6b16f85acbec155e09",
        "939968d62c02408fd0d31c13e5cbc8d499b466b7664caa44820052a6812b0d89",
        "ec7ba0c04c2f76f0ab77ebaebfb54bc0794e353722d90b9b6d2c83b840c5d744",
        "98d5ba2bc50ac37159a82b23a17581c2ea6443da048f3b9041fe511e91739009",
    ),
    "edit loop 120": (
        "a760aa6ef07d2090d5cba622c1407823b19a7f4869b14b82c071ec7f4e05df7c",
        "525cb1ec645cb9919d5f789cf51e04cf3d8fb9843aa4d9bc144566d1725720f2",
        "5b21fa2d82a2411c4995d7c502c7d3a34292258b88a5387a0b4328e68e80cfa5",
        "3c149371ef56e3a68988045f7ba01256decbc091daa56af57923d71e0ac1f905",
        "93a9821ad524366350812c98824dcf125a50c491d535278f523890794a549573",
        "adcee3990fe2eaabe2aa5c43988d59ca5a74c958f41f67104a54b9ad67db5f75",
        "ef78cc0495119af782528d0e8107800119aa6272cf0b70f1d21d7c656c034634",
        "d9acd9d1940ec7286d1176b1be1ff2d7bc13a016c3d72e92e96bb29173ae2bd0",
        "1f84fd3e7922c93ecf3fc1e5260ce04474ea80ac1c3f7ffc5c19c6ef26240ff4",
        "a760aa6ef07d2090d5cba622c1407823b19a7f4869b14b82c071ec7f4e05df7c",
    ),
    "gathered from s": (
        "3ac196d54103a0b2df62aa71bd13514ef3e586db2656d8ef10879b46e64ea5b0",
        "cb33cafe6a129c451e75fdd7b1f990fa928fdc724c76613f93c5df74a975f6ba",
        "cb33cafe6a129c451e75fdd7b1f990fa928fdc724c76613f93c5df74a975f6ba",
        "cb33cafe6a129c451e75fdd7b1f990fa928fdc724c76613f93c5df74a975f6ba",
        "cb33cafe6a129c451e75fdd7b1f990fa928fdc724c76613f93c5df74a975f6ba",
        "cb33cafe6a129c451e75fdd7b1f990fa928fdc724c76613f93c5df74a975f6ba",
        "cb33cafe6a129c451e75fdd7b1f990fa928fdc724c76613f93c5df74a975f6ba",
        "cb33cafe6a129c451e75fdd7b1f990fa928fdc724c76613f93c5df74a975f6ba",
        "cb33cafe6a129c451e75fdd7b1f990fa928fdc724c76613f93c5df74a975f6ba",
        "3ac196d54103a0b2df62aa71bd13514ef3e586db2656d8ef10879b46e64ea5b0",
    ),
    "gathered 3,000 from s[1:]": (
        "285dabed5558a4a1fbb71fdc28fe76d21d737becbb7d6d91aea34e0fc0b1cb1c",
        "963aee35e23289172e27382adafb21f95988da86e3a48d1db296c8de1c600d64",
        "963aee35e23289172e27382adafb21f95988da86e3a48d1db296c8de1c600d64",
        "963aee35e23289172e27382adafb21f95988da86e3a48d1db296c8de1c600d64",
        "963aee35e23289172e27382adafb21f95988da86e3a48d1db296c8de1c600d64",
        "963aee35e23289172e27382adafb21f95988da86e3a48d1db296c8de1c600d64",
        "963aee35e23289172e27382adafb21f95988da86e3a48d1db296c8de1c600d64",
        "963aee35e23289172e27382adafb21f95988da86e3a48d1db296c8de1c600d64",
        "963aee35e23289172e27382adafb21f95988da86e3a48d1db296c8de1c600d64",
        "285dabed5558a4a1fbb71fdc28fe76d21d737becbb7d6d91aea34e0fc0b1cb1c",
    ),
    "gathered 3,000 accesses": (
        "c245ed65b2a6103a7e51d5549f8147384f909bc4f5572095dfbd4f30b2162d4c",
        "5d55d345b668d6637955ad0c2dbaa0a6a1ded0779c8bf76bf2a08bb00145bff7",
        "5d55d345b668d6637955ad0c2dbaa0a6a1ded0779c8bf76bf2a08bb00145bff7",
        "5d55d345b668d6637955ad0c2dbaa0a6a1ded0779c8bf76bf2a08bb00145bff7",
        "5d55d345b668d6637955ad0c2dbaa0a6a1ded0779c8bf76bf2a08bb00145bff7",
        "5d55d345b668d6637955ad0c2dbaa0a6a1ded0779c8bf76bf2a08bb00145bff7",
        "5d55d345b668d6637955ad0c2dbaa0a6a1ded0779c8bf76bf2a08bb00145bff7",
        "5d55d345b668d6637955ad0c2dbaa0a6a1ded0779c8bf76bf2a08bb00145bff7",
        "5d55d345b668d6637955ad0c2dbaa0a6a1ded0779c8bf76bf2a08bb00145bff7",
        "c245ed65b2a6103a7e51d5549f8147384f909bc4f5572095dfbd4f30b2162d4c",
    ),
    "orthogonal vectors": (
        "36a97612bf0bc1db294f4e902b7ccb0ee0e65fce8950dba77346a8d436dcaff7",
        "5cf02b23023b647850d0998432f09c98b442d51307013ae9dffa7b80f08fe6c1",
        "e911848629618379f63622e1f7c670cea12961b6ad3809ec758dc1417656764f",
        "addf12689a959455bc8e45763fa572fb5c6dd81d80bf11b95de52c7a3f8fbae9",
        "b3857f2432449ce060ae1a03b4e74942939f95bef8bb74143faaba7afdb9a076",
        "e3e59307bbecb3ab0b0565f4517aa865d5e19ed8604e303a4081763c3da171d1",
        "3bd7855d4159532032eec5e08e4b1bd9d28710a47916e16d4bfa1d1dc98475c8",
        "d89d8b0d9386e83e0116897da262c157893388f7e5f231b068ade04160de943a",
        "48487bd6703a340d819cc630a7a351f21dc83afc609e54d72cee2b6d93dea3f6",
        "36a97612bf0bc1db294f4e902b7ccb0ee0e65fce8950dba77346a8d436dcaff7",
    ),
}


def _digest(forks: list[Branch], is_leaf: Callable[[Expression], bool] | None) -> str:
    shown = printed_forks(forks) if is_leaf is None else printed_forks(forks, is_leaf)
    text = json.dumps([list(shown.expressions), shown.cut_from])
    return hashlib.sha256(text.encode()).hexdigest()


def written(case: str, monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    """The case's digest at each of its limits, its forks built once."""
    chosen = _CASES[case]
    forks = chosen.build()
    digests = []
    for limit in chosen.limits():
        monkeypatch.setattr("pyct.results.printed.COUNTING_STEPS", limit)
        digests.append(_digest(forks, chosen.is_leaf))
    return tuple(digests)


@pytest.mark.parametrize("case", list(_CASES))
def test_a_line_prints_what_it_printed_whatever_its_steps(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert written(case, monkeypatch) == _WRITTEN[case]
