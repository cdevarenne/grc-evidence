"""A stand-in for llm.LLM: canned outputs, no network, records the requests it was given."""

import json
from typing import Any

from llm import Request


class StubLLM:
    """Returns canned outputs; records the requests it was given."""

    def __init__(self, outputs: dict[str, Any] | Exception) -> None:
        self.outputs = outputs
        self.requests: list[Request] = []

    def complete(self, request: Request) -> Any:
        self.requests.append(request)
        if isinstance(self.outputs, Exception):
            raise self.outputs
        if request.task == "narrate":
            return self.outputs["narrate"]
        gaps = json.loads(request.user.split("\n", 1)[1])
        rules = [g["rule"] for g in gaps]
        return {"proposals": [self.outputs[r] for r in rules if r in self.outputs]}

    def complete_batch(self, requests: dict[str, Request]) -> dict[str, Any]:
        return {cid: self.complete(r) for cid, r in requests.items()}
