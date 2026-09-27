SEP = "-"
OPTIONS = {"sep": "-"}


def of_a_list(parts: list[str]):
    if "-".join(parts) == "a-b":
        return "joined"
    return "other"


def by_a_separator(sep):
    if sep.join(["a", "b"]) == "a+b":
        return "joined"
    return "other"


def by_a_bound_separator(parts):
    if SEP.join(parts) == "a-b":
        return "joined"
    return "other"


def of_a_built_list(a, b):
    if "-".join([a, b.upper()]) == "x-Y":
        return "joined"
    return "other"


def of_split_pieces(s):
    if "-".join(s.split(",")) == "a-b":
        return "joined"
    return "other"


def of_three_split_pieces(s):
    if "-".join(s.split(",")) == "a-b-c":
        return "joined"
    return "other"


def of_a_generator(parts):
    if "".join(p.upper() for p in parts) == "AB":
        return "joined"
    return "other"


def by_a_separator_read_at_run_time(a):
    sep = OPTIONS["sep"]
    if sep.join([a, "b"]) == "x-b":
        return "joined"  # run time
    return "other"  # run time


def by_a_separator_past_cvc5(parts):
    if "\U00030000".join(parts) == "a":
        return "joined"
    return "other"


def of_anything(parts):
    return "-".join(parts)


def of_what_it_is_given(sep, n):
    return sep.join(n)


def of_the_first_piece(s):
    if "-".join(s.split(",")[:1]) == "a":
        return "joined"
    if "," in s:
        if s.endswith("z"):
            return "ends"  # first piece
    return "other"


def of_a_piece_split_again(s):
    if "-".join(s.split(",")[0].split(":")) == "a-b":
        return "joined"
    if "," in s:
        if s.endswith("z"):
            return "ends"  # split again
    return "other"
