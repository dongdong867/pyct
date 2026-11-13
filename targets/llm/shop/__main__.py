"""What `python -m targets.llm.shop` runs. A package's `__main__.py` usually acts when imported, so
the seeds request leaves its class out and an LLM seed cannot name it."""


class Runner:
    def __init__(self, name):
        self.name = name
