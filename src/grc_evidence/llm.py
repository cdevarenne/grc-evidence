"""One small, cost-bounded interface to Claude: replay | record | anthropic | claude-cli (set by LLM_MODE)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grc_evidence.errors import GrcError

Json = dict[str, Any]
MODES = ("replay", "record", "anthropic", "claude-cli")
DEFAULT_MODEL = "claude-haiku-4-5"
# USD per million tokens (input, output), from the official pricing page; verify before relying on totals.
PRICES = {"claude-haiku-4-5": (1.00, 5.00), "claude-sonnet-5": (2.00, 10.00)}
# Per-model request settings. Sonnet 5 thinks by default and thinking tokens count against max_tokens;
# turning it off keeps the bounds, and the comparison with Haiku 4.5 (no thinking), like for like.
MODEL_PARAMS: dict[str, Json] = {"claude-sonnet-5": {"thinking": {"type": "disabled"}}}
CACHE_WRITE, CACHE_READ, BATCH = 1.25, 0.10, 0.50  # multipliers on the input price / on the whole call
CHARS_PER_TOKEN = 3  # conservative: overestimates input tokens for the budget guard
BATCH_POLL_S, BATCH_TIMEOUT_S = 30, 3600  # a stalled batch stops the run after an hour, naming its id
CUSTOM_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # Message Batches API rule for custom_id
REQUEST_TIMEOUT_S = 60.0  # per synchronous call; the SDK default is 10 minutes


class LLMError(GrcError, RuntimeError):
    """A call failed, was refused, was truncated, or has no recorded response."""


class BudgetExceeded(LLMError):
    """The next call could push this run's spend past LLM_BUDGET_USD."""


@dataclass(frozen=True)
class Request:
    """One structured-output call. `system` is stable across runs (cached); `user` is per run."""

    task: str
    system: str
    user: str
    schema: Json
    max_tokens: int

    def key(self, model: str) -> str:
        """sha256(model + prompt): the response-cache and fixture key."""
        payload = json.dumps([model, self.system, self.user, self.schema], sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cost_usd(model: str, usage: Json, batch: bool = False) -> float:
    """Dollar cost of one call from its `usage` block."""
    price_in, price_out = PRICES[model]
    total = (
        usage.get("input_tokens", 0) * price_in
        + usage.get("cache_creation_input_tokens", 0) * price_in * CACHE_WRITE
        + usage.get("cache_read_input_tokens", 0) * price_in * CACHE_READ
        + usage.get("output_tokens", 0) * price_out
    ) / 1_000_000
    return round(total * (BATCH if batch else 1), 6)


def worst_case_usd(model: str, request: Request) -> float:
    """Upper bound for one call: every input char uncached and written to cache, full max_tokens out."""
    tokens_in = (len(request.system) + len(request.user) + len(json.dumps(request.schema))) // CHARS_PER_TOKEN
    return cost_usd(model, {"cache_creation_input_tokens": tokens_in, "output_tokens": request.max_tokens})


@dataclass
class LLM:
    """Structured JSON calls with a response cache, a usage ledger, and a per-run budget guard."""

    mode: str = "replay"
    model: str = DEFAULT_MODEL
    fixtures: Path = Path("tests/fixtures/llm")
    cache: Path = Path("out/llm-cache")
    ledger: Path = Path("out/llm-usage.jsonl")
    budget_usd: float = 1.0
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    client: Any = None  # an anthropic.Anthropic; built lazily so replay never imports the SDK
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    use_cache: bool = True  # False: always call the API (e.g. to measure run-to-run variance); cache untouched

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise LLMError(f"LLM_MODE must be one of {MODES}, not {self.mode!r}")
        if self.model not in PRICES:
            raise LLMError(f"no price for model {self.model!r}; add it to PRICES from the pricing page")

    @classmethod
    def from_env(cls, out: Path = Path("out"), default_model: str = DEFAULT_MODEL) -> LLM:
        """Build from LLM_MODE, LLM_MODEL, LLM_BUDGET_USD (defaults: replay, `default_model`, $1)."""
        return cls(
            mode=os.environ.get("LLM_MODE", "replay"),
            model=os.environ.get("LLM_MODEL", default_model),
            cache=out / "llm-cache",
            ledger=out / "llm-usage.jsonl",
            budget_usd=float(os.environ.get("LLM_BUDGET_USD", "1.0")),
            use_cache=os.environ.get("LLM_NO_CACHE", "") != "1",
        )

    def spent_usd(self) -> float:
        """Billed spend recorded in the ledger for this run."""
        if not self.ledger.is_file():
            return 0.0
        lines = self.ledger.read_text(encoding="utf-8").splitlines()
        return sum(e["cost_usd"] for e in map(json.loads, lines) if e["run_id"] == self.run_id)

    def complete(self, request: Request) -> Json:
        """Parsed JSON output for `request`. Replay and cache hits cost nothing and never touch the network."""
        key = request.key(self.model)
        if self.mode == "replay":
            return self._replay(request, key)
        if self.use_cache and (hit := self.cache / f"{key}.json").is_file():
            recorded = json.loads(hit.read_text(encoding="utf-8"))
            self._log(request, key, recorded["usage"], billed=False)
            return recorded["output"]
        self._guard(request)
        output, usage = self._call_cli(request) if self.mode == "claude-cli" else self._call_api(request)
        recorded = {"task": request.task, "model": self.model, "output": output, "usage": usage}
        if self.use_cache:
            self._save(self.cache / f"{key}.json", recorded)
        if self.mode == "record":
            self._save(self.fixtures / f"{key}.json", recorded)
        self._log(request, key, usage, billed=True, cost=usage.pop("cost_usd", None))
        return output

    def complete_batch(self, requests: dict[str, Request]) -> dict[str, Json]:
        """Outputs keyed by custom id. In anthropic/record mode, cache misses go out as one Message Batch.

        Custom ids are checked against the API's pattern in every mode, so a bad id fails offline, not at the API.
        """
        if bad := [cid for cid in requests if not CUSTOM_ID.match(cid)]:
            raise LLMError(f"batch custom_id must match {CUSTOM_ID.pattern}: {bad[:3]}")
        if self.mode in ("replay", "claude-cli"):
            return {cid: self.complete(r) for cid, r in requests.items()}
        results: dict[str, Json] = {}
        misses: dict[str, Request] = {}
        for cid, r in requests.items():
            if self.use_cache and (self.cache / f"{r.key(self.model)}.json").is_file():
                results[cid] = self.complete(r)
            else:
                misses[cid] = r
        if misses:
            self._guard_total(list(misses.values()), batch=True)
            results |= self._call_batch(misses)
        return results

    # -- internals ---------------------------------------------------------------------------------

    def _replay(self, request: Request, key: str) -> Json:
        path = self.fixtures / f"{key}.json"
        if not path.is_file():
            raise LLMError(f"no recorded response for {request.task} ({key[:12]}); re-record with LLM_MODE=record")
        recorded = json.loads(path.read_text(encoding="utf-8"))
        self._log(request, key, recorded["usage"], billed=False)
        return recorded["output"]

    def _guard_total(self, requests: list[Request], batch: bool = False) -> None:
        """Budget check for a whole batch: the sum of every request's worst case, not each one alone."""
        estimate = sum(worst_case_usd(self.model, r) for r in requests) * (BATCH if batch else 1)
        if self.spent_usd() + estimate > self.budget_usd:
            raise BudgetExceeded(
                f"batch of {len(requests)}: spent ${self.spent_usd():.4f} + up to ${estimate:.4f} would pass "
                f"LLM_BUDGET_USD=${self.budget_usd:.2f}; no call made"
            )

    def _guard(self, request: Request, batch: bool = False) -> None:
        estimate = worst_case_usd(self.model, request) * (BATCH if batch else 1)
        if self.spent_usd() + estimate > self.budget_usd:
            raise BudgetExceeded(
                f"{request.task}: spent ${self.spent_usd():.4f} + up to ${estimate:.4f} would pass "
                f"LLM_BUDGET_USD=${self.budget_usd:.2f}; no call made"
            )

    def _params(self, request: Request) -> Json:
        return {
            "model": self.model,
            "system": [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": request.user}],
            "output_config": {"format": {"type": "json_schema", "schema": request.schema}},
            **MODEL_PARAMS.get(self.model, {}),
        }

    def _client(self) -> Any:
        if self.client is None:
            import anthropic  # optional dependency: `uv sync --extra llm`

            self.client = anthropic.Anthropic()
        return self.client

    def _parse(self, message: Any, task: str) -> tuple[Json, Json]:
        if message.stop_reason != "end_turn":
            raise LLMError(f"{task}: stop_reason {message.stop_reason!r}; output rejected")
        try:
            output = json.loads(next(b.text for b in message.content if b.type == "text"))
        except (StopIteration, json.JSONDecodeError) as e:  # no text block, or text that is not JSON
            raise LLMError(f"{task}: response is not one JSON text block ({type(e).__name__}); output rejected") from e
        usage = {
            k: getattr(message.usage, k, 0) or 0
            for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        }
        return output, usage

    def _call_api(self, request: Request) -> tuple[Json, Json]:
        message = self._client().messages.create(
            **self._params(request), max_tokens=request.max_tokens, timeout=REQUEST_TIMEOUT_S
        )
        return self._parse(message, request.task)

    def _call_batch(self, requests: dict[str, Request]) -> dict[str, Json]:
        client = self._client()
        batch = client.messages.batches.create(
            requests=[
                {"custom_id": cid, "params": {**self._params(r), "max_tokens": r.max_tokens}}
                for cid, r in requests.items()
            ]
        )
        print(f"llm: batch {batch.id} submitted ({len(requests)} requests); polling every {BATCH_POLL_S} s", file=sys.stderr)
        deadline = time.monotonic() + BATCH_TIMEOUT_S
        while (batch := client.messages.batches.retrieve(batch.id)).processing_status != "ended":
            if time.monotonic() > deadline:
                raise LLMError(f"batch {batch.id}: not ended after {BATCH_TIMEOUT_S} s ({batch.processing_status}); its results stay retrievable")
            print(f"llm: batch {batch.id} {batch.processing_status}: {batch.request_counts}", file=sys.stderr)
            time.sleep(BATCH_POLL_S)
        print(f"llm: batch {batch.id} ended", file=sys.stderr)
        outputs: dict[str, Json] = {}
        for result in client.messages.batches.results(batch.id):  # any order: key by custom_id
            r = requests[result.custom_id]
            if result.result.type != "succeeded":
                raise LLMError(f"{r.task} {result.custom_id}: batch result {result.result.type}")
            output, usage = self._parse(result.result.message, r.task)
            key = r.key(self.model)
            recorded = {"task": r.task, "model": self.model, "output": output, "usage": usage}
            if self.use_cache:
                self._save(self.cache / f"{key}.json", recorded)
            if self.mode == "record":
                self._save(self.fixtures / f"{key}.json", recorded)
            self._log(r, key, usage, billed=True, batch=True)
            outputs[result.custom_id] = output
        return outputs

    def _call_cli(self, request: Request) -> tuple[Json, Json]:
        """Claude Code headless mode: uses the Claude plan, not API credit. Dev loop only."""
        argv = [
            "claude", "-p", "--output-format", "json", "--model", self.model,
            "--system-prompt", request.system, "--json-schema", json.dumps(request.schema),
        ]
        proc = self.runner(argv, input=request.user, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise LLMError(f"{request.task}: claude exited {proc.returncode}: {proc.stderr.strip()[-300:]}")
        try:
            doc = json.loads(proc.stdout)
            output = doc.get("structured_output") or json.loads(doc["result"])
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
            raise LLMError(f"{request.task}: claude returned no JSON result ({type(e).__name__}); output rejected") from e
        usage = {k: doc.get("usage", {}).get(k, 0) for k in ("input_tokens", "output_tokens",
                 "cache_creation_input_tokens", "cache_read_input_tokens")}
        usage["cost_usd"] = 0.0  # plan usage, not API credit; the plan's own limits apply
        return output, usage

    def _save(self, path: Path, doc: Json) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _log(
        self, request: Request, key: str, usage: Json, billed: bool, batch: bool = False, cost: float | None = None
    ) -> None:
        if cost is None:
            cost = cost_usd(self.model, usage, batch) if billed else 0.0
        entry = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "task": request.task,
            "mode": self.mode,
            "model": self.model,
            "prompt_hash": key,
            **{k: usage.get(k, 0) for k in ("input_tokens", "output_tokens",
               "cache_creation_input_tokens", "cache_read_input_tokens")},
            "batch": batch,
            "billed": billed,
            "cost_usd": cost,
        }
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
