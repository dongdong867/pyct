"""The loop shapes the loop rule is checked on, each a module that defines `f`: one per place a
loop can end, start or sit, and one per kind of assignment of a comprehension."""

# the loops, and where each sits: last in a function, in another loop, in an `if`, a `try`, a
# `with` or a `match`, or at module level or in a class body, where it is no piece
LOOPS: dict[str, str] = {
    "for": ("def f(xs):\n    t = 0\n    for x in xs:\n        t += x\n    return t\n"),
    "while": ("def f(n):\n    i = 0\n    while i < n:\n        i += 1\n    return i\n"),
    "while_true_break": (
        "def f(n):\n"
        "    i = 0\n"
        "    while True:\n"
        "        i += 1\n"
        "        if i > n:\n"
        "            break\n"
        "    return i\n"
    ),
    "while_1_break_last": (
        "def f(n):\n    while 1:\n        n -= 1\n        if n:\n            break\n"
    ),
    "for_continue": (
        "def f(xs):\n"
        "    t = 0\n"
        "    for x in xs:\n"
        "        if x < 0:\n"
        "            continue\n"
        "        t += x\n"
        "    return t\n"
    ),
    "for_else_break": (
        "def f(xs):\n"
        "    for x in xs:\n"
        "        if x == 3:\n"
        "            break\n"
        "    else:\n"
        "        x = None\n"
        "    return x\n"
    ),
    "while_else_break": (
        "def f(i):\n"
        "    while i < 9:\n"
        "        if i == 3:\n"
        "            break\n"
        "        i += 1\n"
        "    else:\n"
        "        i = None\n"
        "    return i\n"
    ),
    "nested_break_in_else": (
        "def f(xss):\n"
        "    n = 0\n"
        "    for xs in xss:\n"
        "        for x in xs:\n"
        "            if x:\n"
        "                break\n"
        "            n += 1\n"
        "        else:\n"
        "            break\n"
        "        n -= 1\n"
        "    return n\n"
    ),
    "for_last_in_function": ("def f(xs):\n    for x in xs:\n        g(x)\n"),
    "while_last_in_function": ("def f(n):\n    while n:\n        n -= 1\n"),
    "for_last_in_if": (
        "def f(xs, c):\n"
        "    if c:\n"
        "        for x in xs:\n"
        "            g(x)\n"
        "    else:\n"
        "        h()\n"
        "    return 1\n"
    ),
    "while_last_in_if": (
        "def f(n, c):\n"
        "    if c:\n"
        "        while n:\n"
        "            n -= 1\n"
        "    else:\n"
        "        h()\n"
        "    return 1\n"
    ),
    "while_last_in_if_no_else": (
        "def f(n, c):\n    if c:\n        while n:\n            n -= 1\n    return 1\n"
    ),
    "for_last_in_for": (
        "def f(xss):\n    for xs in xss:\n        for x in xs:\n            g(x)\n    return 0\n"
    ),
    "while_last_in_for": (
        "def f(xs):\n    for n in xs:\n        while n:\n            n -= 1\n    return 0\n"
    ),
    "for_last_in_while": (
        "def f(n, xs):\n"
        "    while n:\n"
        "        n -= 1\n"
        "        for x in xs:\n"
        "            g(x)\n"
        "    return 0\n"
    ),
    "while_last_in_while": (
        "def f(n, m):\n"
        "    while n:\n"
        "        n -= 1\n"
        "        while m:\n"
        "            m -= 1\n"
        "    return 0\n"
    ),
    "for_last_in_try": (
        "def f(xs):\n"
        "    try:\n"
        "        for x in xs:\n"
        "            g(x)\n"
        "    except E:\n"
        "        pass\n"
        "    return 0\n"
    ),
    "while_last_in_try_finally": (
        "def f(n):\n"
        "    try:\n"
        "        while n:\n"
        "            n -= 1\n"
        "    finally:\n"
        "        g()\n"
        "    return 0\n"
    ),
    "for_last_in_with": (
        "def f(xs):\n    with cm():\n        for x in xs:\n            g(x)\n    return 0\n"
    ),
    "while_last_in_with": (
        "def f(n):\n    with cm():\n        while n:\n            n -= 1\n    return 0\n"
    ),
    "for_followed_later": (
        "def f(xs):\n    for x in xs:\n        g(x)\n\n    # note\n\n    return x\n"
    ),
    "while_followed_later": (
        "def f(n):\n    while n:\n        n -= 1\n\n    # note\n\n    return n\n"
    ),
    "one_line": ("def f(y):\n    for x in y: pass\n    while y: y -= 1\n    return 0\n"),
    "one_line_break": ("def f(y):\n    for x in y: break\n    while y: break\n    return 0\n"),
    "return_raise_in_body": (
        "def f(xs):\n"
        "    for x in xs:\n"
        "        if x:\n"
        "            return x\n"
        "        if x is None:\n"
        "            raise ValueError\n"
        "    return 0\n"
    ),
    "while_return_in_body": (
        "def f(n):\n"
        "    while n:\n"
        "        if n == 3:\n"
        "            return n\n"
        "        n -= 1\n"
        "    return 0\n"
    ),
    "generator": (
        "def f(xs):\n"
        "    t = 0\n"
        "    for x in xs:\n"
        "        t += x\n"
        "        yield t\n"
        "    while t:\n"
        "        t -= 1\n"
        "        yield t\n"
    ),
    "async_for": (
        "async def f(xs):\n    t = 0\n    async for x in xs:\n        t += x\n    return t\n"
    ),
    "async_for_last_break": (
        "async def f(xs):\n    async for x in xs:\n        if x:\n            break\n"
    ),
    "module_level": ("t = 0\nfor x in range(3):\n    t += x\nwhile t:\n    t -= 1\nprint(t)\n"),
    "module_level_last": ("t = 0\nwhile t:\n    t -= 1\nfor x in range(3):\n    t += x\n"),
    "class_body": (
        "class C:\n"
        "    t = 0\n"
        "    for x in range(3):\n"
        "        t += x\n"
        "    while t > 1:\n"
        "        t -= 1\n"
    ),
    "spread_headers": (
        "def f(n, i):\n"
        "    for x in range(\n"
        "            n):\n"
        "        g(x)\n"
        "    while (i <\n"
        "           n):\n"
        "        i += 1\n"
        "    return i\n"
    ),
    "while_and_or": (
        "def f(s, i, n):\n"
        "    while i < n and s[i] != 'z' or i == 0:\n"
        "        i += 1\n"
        "    return i\n"
    ),
    "while_not": ("def f(s):\n    while not s:\n        s = g()\n    return s\n"),
    "break_in_try_finally": (
        "def f(xs):\n"
        "    for x in xs:\n"
        "        try:\n"
        "            if x:\n"
        "                break\n"
        "        finally:\n"
        "            g()\n"
        "    return 0\n"
    ),
    "break_in_with": (
        "def f(n):\n"
        "    while n:\n"
        "        with cm():\n"
        "            if n == 2:\n"
        "                break\n"
        "        n -= 1\n"
        "    return 0\n"
    ),
    "else_returns": (
        "def f(xs):\n"
        "    for x in xs:\n"
        "        if x:\n"
        "            break\n"
        "    else:\n"
        "        return None\n"
        "    return x\n"
    ),
    "loop_last_in_match": (
        "def f(v, xs):\n"
        "    match v:\n"
        "        case 1:\n"
        "            for x in xs:\n"
        "                g(x)\n"
        "        case _:\n"
        "            while xs:\n"
        "                xs.pop()\n"
        "    return 0\n"
    ),
    "while_last_in_else": (
        "def f(c, n):\n    if c:\n        g()\n    else:\n        while n:\n            n -= 1\n"
    ),
    "while_last_in_if_in_for": (
        "def f(xs, c):\n"
        "    for n in xs:\n"
        "        if c:\n"
        "            while n:\n"
        "                n -= 1\n"
        "    return 0\n"
    ),
    "while_then_continue": (
        "def f(xs):\n"
        "    for n in xs:\n"
        "        while n:\n"
        "            n -= 1\n"
        "        continue\n"
        "    return 0\n"
    ),
    "for_last_in_while_true": (
        "def f(xs):\n    while True:\n        for x in xs:\n            g(x)\n"
    ),
    "while_true_no_break_last": ("def f(n):\n    while True:\n        n = g(n)\n"),
    "while_in_except": (
        "def f(n):\n"
        "    try:\n"
        "        g()\n"
        "    except E:\n"
        "        while n:\n"
        "            n -= 1\n"
        "    return n\n"
    ),
    # found by the corpus with the switch on: where the false outcome of a while's test lands
    # depends on the branches around it
    "while_chained": (
        "def f(m, n):\n"
        "    while m % 2 == n % 2 == 0:\n"
        "        m //= 2\n"
        "        n //= 2\n"
        "    return m\n"
    ),
    "while_last_in_elif_in_with": (
        "def f(self, block, timeout):\n"
        "    with cm():\n"
        "        if self.maxsize > 0:\n"
        "            if not block:\n"
        "                g()\n"
        "            elif timeout is None:\n"
        "                while self.size() >= self.maxsize:\n"
        "                    self.wait()\n"
        "            else:\n"
        "                h()\n"
        "        g()\n"
    ),
    "while_and_last_in_if_in_for": (
        "def f(n, line, xs):\n"
        "    for x in xs:\n"
        "        if n > 0:\n"
        "            while n > 0 and line:\n"
        "                n = n - 1\n"
        "        else:\n"
        "            h()\n"
        "        g()\n"
    ),
    "while_and_assign_hooked": (
        "def f(n, s):\n"
        "    while n > 0 and s:\n"
        "        n -= 1\n"
        "        s = [c for c in s if c != n]\n"
        "    return s\n"
    ),
}

# the assignments of a comprehension
ASSIGNMENTS: dict[str, str] = {
    "genexp_sum": ("def f(s):\n    t = sum(1 for c in s if c == 'z')\n    return t\n"),
    "listcomp": ("def f(s):\n    u = [c for c in s if c]\n    return u\n"),
    "dictcomp_ann": ("def f(s):\n    v: dict = {c: 1 for c in s}\n    return v\n"),
    "augassign": ("def f(s, t):\n    t += sum(1 for c in s)\n    return t\n"),
    "spread": ("def f(s):\n    w = sum(\n        1 for c in s\n        if c)\n    return w\n"),
    "method_value": ("def f(s):\n    w = (s\n        .join(c for c in s))\n    return w\n"),
    "attr_first": ("def f(o, s):\n    w = (o\n         .m)([c for c in s])\n    return w\n"),
    "module_level": ("s = 'abz'\nt = sum(1 for c in s if c == 'z')\n"),
    "last_in_function": ("def f(s):\n    t = [c for c in s]\n"),
    "unpack_target": ("def f(s):\n    a, b = [c for c in s][:2]\n    return a\n"),
}
