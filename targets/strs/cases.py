def shape(s: str) -> str:
    if s.upper() == "AB":
        return "upper"
    if s.lower() == "cd":
        return "lower"
    if s.capitalize() == "Ef":
        return "capitalize"
    if s.title() == "Gh Ij":
        return "title"
    if s.swapcase() == "kL":
        return "swapcase"
    if s.casefold() == "mn":
        return "casefold"
    if s.strip() == "op":
        return "strip"
    if s.lstrip("-") == "qr":
        return "lstrip"
    if s.rstrip() == "st":
        return "rstrip"
    if s.zfill(3) == "007":
        return "zfill"
    if s.center(5, "*") == "*uv**":
        return "center"
    if s.ljust(3, ".") == "w..":
        return "ljust"
    if s.rjust(4) == "  yz":
        return "rjust"
    return "other"
