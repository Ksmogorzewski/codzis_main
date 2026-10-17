#!/usr/bin/env python3
"""
Orchestrator — ties the pipeline together and runs the tagging.

Flow per chunk:
    build messages -> DeepSeek call (json mode, thinking disabled)
    -> parse/validate -> save per-event results to tagged.jsonl

Also reports token usage per chunk and in total.

Usage (from the project root):
    python3 -m tagger.orchestrator --limit 20     # tag first 20 events
    python3 -m tagger.orchestrator                # tag everything
"""

import argparse
import json
import time
from pathlib import Path

from .chunker import chunk
from .client import DeepSeekClient
from .config import DATA_DIR
from .parser import parse_response
from .prompt import DIMENSIONS, build_messages

INPUT_PATH = DATA_DIR / "events_for_model.json"
OUTPUT_PATH = DATA_DIR / "tagged.jsonl"

TARGET_TOKENS = 5000
MAX_RETRIES = 3
# deepseek-flash defaults to thinking mode; disable it for fast/cheap tagging.
EXTRA_BODY = {"thinking": {"type": "disabled"}}

# Approx pricing (USD / 1M tokens, off-peak, cache miss) for deepseek-flash.
PRICE_INPUT_PER_M = 0.15
PRICE_OUTPUT_PER_M = 0.60


class Orchestrator:
    def __init__(
        self,
        client: DeepSeekClient | None = None,
        dimensions: dict | None = None,
        target_tokens: int = TARGET_TOKENS,
        max_retries: int = MAX_RETRIES,
        output_path: str | Path | None = None,
    ):
        self.client = client or DeepSeekClient()
        self.dimensions = dimensions or DIMENSIONS
        self.target_tokens = target_tokens
        self.max_retries = max_retries
        self.output_path = Path(output_path) if output_path else OUTPUT_PATH

    def tag_chunk(self, chunk: list[dict]) -> tuple[dict, object]:
        """One API call for one chunk. Returns (parsed, usage)."""
        messages = build_messages(chunk, self.dimensions)
        response = self.client.chat(messages, json_mode=True, extra_body=EXTRA_BODY)
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        expected = [r["id"] for r in chunk]
        parsed = parse_response(text, expected, self.dimensions)
        return parsed, usage

    def run(self, records: list[dict]) -> dict:
        """Tag all records; write results incrementally; return a summary."""
        chunks = chunk(records, self.target_tokens)
        results = {}
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        failures = []
        missing_total = 0
        unknown_total = 0

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as out:
            for i, c in enumerate(chunks):
                parsed, usage = self._call_with_retry(c)
                if parsed is None:
                    failures.append({"chunk": i, "events": len(c)})
                    continue

                results.update(parsed["results"])
                missing_total += len(parsed["missing_ids"])
                unknown_total += len(parsed["unknown_values"])

                if usage:
                    total["prompt_tokens"] += usage.prompt_tokens or 0
                    total["completion_tokens"] += usage.completion_tokens or 0
                    total["total_tokens"] += usage.total_tokens or 0

                # write one line per event (id + dimension values)
                for r in c:
                    eid = r["id"]
                    out.write(json.dumps(
                        {"id": eid, **parsed["results"].get(eid, {})},
                        ensure_ascii=False,
                    ) + "\n")

                print(f"  chunk {i + 1}/{len(chunks)}: "
                      f"{len(c)} events, "
                      f"{usage.prompt_tokens if usage else '?'} in / "
                      f"{usage.completion_tokens if usage else '?'} out tokens")

        total["events_tagged"] = len(results)
        total["chunks"] = len(chunks)
        total["failed_chunks"] = len(failures)
        total["missing_events"] = missing_total
        total["unknown_values_dropped"] = unknown_total
        total["approx_cost_usd"] = (
            total["prompt_tokens"] * PRICE_INPUT_PER_M / 1e6
            + total["completion_tokens"] * PRICE_OUTPUT_PER_M / 1e6
        )
        return {"results": results, "usage": total, "failures": failures}

    def _call_with_retry(self, chunk: list[dict]):
        """Retry with exponential backoff; return (parsed, usage) or (None, None)."""
        for attempt in range(self.max_retries):
            try:
                return self.tag_chunk(chunk)
            except Exception as exc:  # noqa: BLE001 - report upstream
                print(f"    attempt {attempt + 1} failed: {exc}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run event tagging via DeepSeek.")
    parser.add_argument("--limit", type=int, default=None,
                        help="tag only the first N events (e.g. 20 for a test)")
    parser.add_argument("--target-tokens", type=int, default=TARGET_TOKENS)
    args = parser.parse_args()

    records = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if args.limit:
        records = records[: args.limit]

    print(f"Tagging {len(records)} events "
          f"(target ~{args.target_tokens} tokens/chunk)...\n")

    orch = Orchestrator(target_tokens=args.target_tokens)
    summary = orch.run(records)
    usage = summary["usage"]

    print()
    print("=== SUMMARY ===")
    print(f"events tagged        : {usage['events_tagged']}")
    print(f"chunks               : {usage['chunks']} (failed: {usage['failed_chunks']})")
    print(f"prompt tokens        : {usage['prompt_tokens']}")
    print(f"completion tokens    : {usage['completion_tokens']}")
    print(f"total tokens         : {usage['total_tokens']}")
    print(f"missing events       : {usage['missing_events']}")
    print(f"unknown values dropped: {usage['unknown_values_dropped']}")
    print(f"approx cost (USD)    : ${usage['approx_cost_usd']:.4f}")

    if args.limit:  # show actual results for a small/test run
        print()
        print("=== RESULTS ===")
        for r in records:
            eid = r["id"]
            res = summary["results"].get(eid, {})
            print(f"  {(r['title'] or '')[:50]}")
            for dim, val in res.items():
                print(f"      {dim}: {val}")

    print(f"\nWrote -> {orch.output_path}")


if __name__ == "__main__":
    main()
