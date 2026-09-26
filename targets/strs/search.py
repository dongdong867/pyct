def kind(s: str, t: str) -> str:
    if "@" in s:
        return "email"
    if s.startswith("http"):
        return "link"
    if s.endswith(".py"):
        return "script"
    if s.find(":") == 4:
        return "scheme"
    if s.rfind("/") > 0:
        return "path"
    if s.count("-") == 2:
        return "date"
    if t in s:
        return "tagged"
    if s.rindex("#") > 3:
        return "anchor"
    if s.index("=") == 0:
        return "setting"
    return "other"
