import builtins

# a plain range and a plain dict, whose answers the tracked ones are compared with
PLAIN = range(3)
OTHER = range(3)
PLAIN_DICT = {"k": 1}

# Python's view types, by the names Python gives them
dict_keys = type({}.keys())
dict_values = type({}.values())
dict_items = type({}.items())


def range_by_type(r):
    return [
        type(r).__bool__(r),
        type(r).__contains__(r, 1),
        type(r).__eq__(r, OTHER),
        type(r).__ge__(r, OTHER),
        type(r).__getattribute__(r, "stop"),
        type(r).__getitem__(r, 1),
        type(r).__gt__(r, OTHER),
        type(r).__hash__(r),
        list(type(r).__iter__(r)),
        type(r).__le__(r, OTHER),
        type(r).__len__(r),
        type(r).__lt__(r, OTHER),
        type(r).__ne__(r, OTHER),
        type(r).__reduce__(r),
        type(r).__repr__(r),
        list(type(r).__reversed__(r)),
        type(r).count(r, 1),
        type(r).index(r, 1),
    ]


def range_by_class(r):
    return [
        r.__class__.__bool__(r),
        r.__class__.__contains__(r, 1),
        r.__class__.__eq__(r, OTHER),
        r.__class__.__ge__(r, OTHER),
        r.__class__.__getattribute__(r, "stop"),
        r.__class__.__getitem__(r, 1),
        r.__class__.__gt__(r, OTHER),
        r.__class__.__hash__(r),
        list(r.__class__.__iter__(r)),
        r.__class__.__le__(r, OTHER),
        r.__class__.__len__(r),
        r.__class__.__lt__(r, OTHER),
        r.__class__.__ne__(r, OTHER),
        r.__class__.__reduce__(r),
        r.__class__.__repr__(r),
        list(r.__class__.__reversed__(r)),
        r.__class__.count(r, 1),
        r.__class__.index(r, 1),
    ]


def range_by_name(r):
    return [
        range.__bool__(r),
        range.__contains__(r, 1),
        range.__eq__(r, OTHER),
        range.__ge__(r, OTHER),
        range.__getattribute__(r, "stop"),
        range.__getitem__(r, 1),
        range.__gt__(r, OTHER),
        range.__hash__(r),
        list(range.__iter__(r)),
        range.__le__(r, OTHER),
        range.__len__(r),
        range.__lt__(r, OTHER),
        range.__ne__(r, OTHER),
        range.__reduce__(r),
        range.__repr__(r),
        list(range.__reversed__(r)),
        range.count(r, 1),
        range.index(r, 1),
    ]


def range_by_module(r):
    return [
        builtins.range.__bool__(r),
        builtins.range.__contains__(r, 1),
        builtins.range.__eq__(r, OTHER),
        builtins.range.__ge__(r, OTHER),
        builtins.range.__getattribute__(r, "stop"),
        builtins.range.__getitem__(r, 1),
        builtins.range.__gt__(r, OTHER),
        builtins.range.__hash__(r),
        list(builtins.range.__iter__(r)),
        builtins.range.__le__(r, OTHER),
        builtins.range.__len__(r),
        builtins.range.__lt__(r, OTHER),
        builtins.range.__ne__(r, OTHER),
        builtins.range.__reduce__(r),
        builtins.range.__repr__(r),
        list(builtins.range.__reversed__(r)),
        builtins.range.count(r, 1),
        builtins.range.index(r, 1),
    ]


RANGE_WAYS = (range_by_type, range_by_class, range_by_name, range_by_module)


def range_methods(n):
    r = range(n)
    for way in RANGE_WAYS:
        if way(r) != way(PLAIN):
            return "differs"
    return "same"


def keys_by_type(v):
    return [
        type(v).__and__(v, {"k"}),
        type(v).__contains__(v, "k"),
        type(v).__eq__(v, {"k"}),
        type(v).__ge__(v, {"k"}),
        type(v).__gt__(v, set()),
        list(type(v).__iter__(v)),
        type(v).__le__(v, {"k"}),
        type(v).__len__(v),
        type(v).__lt__(v, {"k", "j"}),
        type(v).__ne__(v, {"k"}),
        type(v).__or__(v, {"j"}),
        type(v).__rand__(v, {"k"}),
        type(v).__repr__(v),
        list(type(v).__reversed__(v)),
        type(v).__ror__(v, {"j"}),
        type(v).__rsub__(v, {"k", "j"}),
        type(v).__rxor__(v, {"j"}),
        type(v).__sub__(v, {"j"}),
        type(v).__xor__(v, {"j"}),
        type(v).isdisjoint(v, ["a"]),
    ]


def keys_by_class(v):
    return [
        v.__class__.__and__(v, {"k"}),
        v.__class__.__contains__(v, "k"),
        v.__class__.__eq__(v, {"k"}),
        v.__class__.__ge__(v, {"k"}),
        v.__class__.__gt__(v, set()),
        list(v.__class__.__iter__(v)),
        v.__class__.__le__(v, {"k"}),
        v.__class__.__len__(v),
        v.__class__.__lt__(v, {"k", "j"}),
        v.__class__.__ne__(v, {"k"}),
        v.__class__.__or__(v, {"j"}),
        v.__class__.__rand__(v, {"k"}),
        v.__class__.__repr__(v),
        list(v.__class__.__reversed__(v)),
        v.__class__.__ror__(v, {"j"}),
        v.__class__.__rsub__(v, {"k", "j"}),
        v.__class__.__rxor__(v, {"j"}),
        v.__class__.__sub__(v, {"j"}),
        v.__class__.__xor__(v, {"j"}),
        v.__class__.isdisjoint(v, ["a"]),
    ]


def keys_by_name(v):
    return [
        dict_keys.__and__(v, {"k"}),
        dict_keys.__contains__(v, "k"),
        dict_keys.__eq__(v, {"k"}),
        dict_keys.__ge__(v, {"k"}),
        dict_keys.__gt__(v, set()),
        list(dict_keys.__iter__(v)),
        dict_keys.__le__(v, {"k"}),
        dict_keys.__len__(v),
        dict_keys.__lt__(v, {"k", "j"}),
        dict_keys.__ne__(v, {"k"}),
        dict_keys.__or__(v, {"j"}),
        dict_keys.__rand__(v, {"k"}),
        dict_keys.__repr__(v),
        list(dict_keys.__reversed__(v)),
        dict_keys.__ror__(v, {"j"}),
        dict_keys.__rsub__(v, {"k", "j"}),
        dict_keys.__rxor__(v, {"j"}),
        dict_keys.__sub__(v, {"j"}),
        dict_keys.__xor__(v, {"j"}),
        dict_keys.isdisjoint(v, ["a"]),
    ]


def values_by_type(v):
    return [
        list(type(v).__iter__(v)),
        type(v).__len__(v),
        type(v).__repr__(v),
        list(type(v).__reversed__(v)),
    ]


def values_by_class(v):
    return [
        list(v.__class__.__iter__(v)),
        v.__class__.__len__(v),
        v.__class__.__repr__(v),
        list(v.__class__.__reversed__(v)),
    ]


def values_by_name(v):
    return [
        list(dict_values.__iter__(v)),
        dict_values.__len__(v),
        dict_values.__repr__(v),
        list(dict_values.__reversed__(v)),
    ]


def items_by_type(v):
    return [
        type(v).__and__(v, {("k", 1)}),
        type(v).__contains__(v, ("k", 1)),
        type(v).__eq__(v, {("k", 1)}),
        type(v).__ge__(v, {("k", 1)}),
        type(v).__gt__(v, set()),
        list(type(v).__iter__(v)),
        type(v).__le__(v, {("k", 1)}),
        type(v).__len__(v),
        type(v).__lt__(v, {("k", 1), ("j", 2)}),
        type(v).__ne__(v, {("k", 1)}),
        type(v).__or__(v, {("j", 2)}),
        type(v).__rand__(v, {("k", 1)}),
        type(v).__repr__(v),
        list(type(v).__reversed__(v)),
        type(v).__ror__(v, {("j", 2)}),
        type(v).__rsub__(v, {("k", 1), ("j", 2)}),
        type(v).__rxor__(v, {("j", 2)}),
        type(v).__sub__(v, {("j", 2)}),
        type(v).__xor__(v, {("j", 2)}),
        type(v).isdisjoint(v, [("a", 1)]),
    ]


def items_by_class(v):
    return [
        v.__class__.__and__(v, {("k", 1)}),
        v.__class__.__contains__(v, ("k", 1)),
        v.__class__.__eq__(v, {("k", 1)}),
        v.__class__.__ge__(v, {("k", 1)}),
        v.__class__.__gt__(v, set()),
        list(v.__class__.__iter__(v)),
        v.__class__.__le__(v, {("k", 1)}),
        v.__class__.__len__(v),
        v.__class__.__lt__(v, {("k", 1), ("j", 2)}),
        v.__class__.__ne__(v, {("k", 1)}),
        v.__class__.__or__(v, {("j", 2)}),
        v.__class__.__rand__(v, {("k", 1)}),
        v.__class__.__repr__(v),
        list(v.__class__.__reversed__(v)),
        v.__class__.__ror__(v, {("j", 2)}),
        v.__class__.__rsub__(v, {("k", 1), ("j", 2)}),
        v.__class__.__rxor__(v, {("j", 2)}),
        v.__class__.__sub__(v, {("j", 2)}),
        v.__class__.__xor__(v, {("j", 2)}),
        v.__class__.isdisjoint(v, [("a", 1)]),
    ]


def items_by_name(v):
    return [
        dict_items.__and__(v, {("k", 1)}),
        dict_items.__contains__(v, ("k", 1)),
        dict_items.__eq__(v, {("k", 1)}),
        dict_items.__ge__(v, {("k", 1)}),
        dict_items.__gt__(v, set()),
        list(dict_items.__iter__(v)),
        dict_items.__le__(v, {("k", 1)}),
        dict_items.__len__(v),
        dict_items.__lt__(v, {("k", 1), ("j", 2)}),
        dict_items.__ne__(v, {("k", 1)}),
        dict_items.__or__(v, {("j", 2)}),
        dict_items.__rand__(v, {("k", 1)}),
        dict_items.__repr__(v),
        list(dict_items.__reversed__(v)),
        dict_items.__ror__(v, {("j", 2)}),
        dict_items.__rsub__(v, {("k", 1), ("j", 2)}),
        dict_items.__rxor__(v, {("j", 2)}),
        dict_items.__sub__(v, {("j", 2)}),
        dict_items.__xor__(v, {("j", 2)}),
        dict_items.isdisjoint(v, [("a", 1)]),
    ]


VIEW_WAYS = (
    ("keys", (keys_by_type, keys_by_class, keys_by_name)),
    ("values", (values_by_type, values_by_class, values_by_name)),
    ("items", (items_by_type, items_by_class, items_by_name)),
)


def view_methods(d):
    for name, ways in VIEW_WAYS:
        for way in ways:
            if way(getattr(d, name)()) != way(getattr(PLAIN_DICT, name)()):
                return "differs"
    return "same"


def through(n, d):
    r = range(n)
    keys = d.keys()
    size = type(r).__len__(r)
    at = range.index(r, 0)
    apart = type(keys).isdisjoint(keys, ["a"])
    held = keys.__class__.__contains__(keys, "a")
    return [size, at, apart, held]


def direct(n, d):
    r = range(n)
    keys = d.keys()
    size = r.__len__()
    at = r.index(0)
    apart = keys.isdisjoint(["a"])
    held = keys.__contains__("a")
    return [size, at, apart, held]


def lookup(d):
    if type(d.keys()).__contains__(d.keys(), "a"):
        return "found"
    return "missing"


def walk(n):
    for i in range.__iter__(range(n)):
        if i == 2:
            return "two"
    return "short"


def refused(call):
    try:
        call()
    except Exception as error:
        return f"{type(error).__name__}: {error}"
    return None


def refusals(r, d):
    keys, values, items = d.keys(), d.values(), d.items()
    return [
        refused(lambda: range.__len__(keys)),
        refused(lambda: type(keys).__len__(values)),
        refused(lambda: type(keys).isdisjoint(r, ())),
        refused(lambda: range.index(items, 0)),
        refused(lambda: type(r).__len__(r, 1)),
        refused(lambda: range.__contains__(r)),
        refused(lambda: type(keys).__iter__(keys, 1)),
        refused(lambda: range.__contains__(r, key=0)),
        refused(lambda: type(keys).__contains__(keys, key="k")),
    ]


def wrong(n, d):
    if refusals(range(n), d) == refusals(PLAIN, PLAIN_DICT):
        return "same"
    return "differs"


def index(n):
    return range.index(range(n), 99)


def disjoint(d):
    return type(d.keys()).isdisjoint(d.keys(), 5)
