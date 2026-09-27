from targets.intercept import across_helper


class Judge:
    def rule(self, b: bool) -> str:
        if b is True:
            return "method"
        return "no"


def spread(x: int) -> list[str]:
    b = x > 5

    def nested() -> str:
        if b is True:
            return "nested"
        return "no"

    # imported only when the target is called, so a forked input imports it for the first time
    from targets.intercept import across_lazy

    return [across_helper.rule(b), Judge().rule(b), nested(), across_lazy.rule(b)]
