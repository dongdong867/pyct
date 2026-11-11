"""The worker: one ask in a short process of its own, ``python -I -m pyct.llm.worker``.

It reads one JSON request on stdin, ``{"provider", "model", "text", "out_tokens"}``, asks
through the provider's adapter, and prints one JSON line: ``{"text", "in", "out"}``, or
``{"error", "status"}`` with the error's class name and HTTP status. The error's own text is
never printed, so no header or key can leave through it. No SDK module, thread or socket stays
in pyct's process, which kills this one at its limit.
"""

from __future__ import annotations

import importlib
import json
import sys

from pyct.llm.providers import PROVIDERS


def main() -> int:
    """Answer the request on stdin on stdout. Exit 0 whether the provider answered or not."""
    request = json.loads(sys.stdin.read())
    adapter = importlib.import_module(PROVIDERS[request["provider"]].adapter)
    try:
        text, tokens_in, tokens_out = adapter.ask(
            request["model"], request["text"], request["out_tokens"]
        )
    except Exception as error:  # noqa: BLE001 - every SDK error becomes a value pyct reports
        status = getattr(error, "status_code", None)
        reply: dict[str, object] = {"error": type(error).__name__, "status": status}
    else:
        reply = {"text": text, "in": tokens_in, "out": tokens_out}
    sys.stdout.write(json.dumps(reply) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
