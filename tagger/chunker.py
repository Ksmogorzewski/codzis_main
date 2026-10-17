#!/usr/bin/env python3
"""
Token-budgeted chunking for the tagging pipeline.

Greedy packing: fill each chunk until adding the next record would exceed the
token budget, then start a new chunk. A record larger than the budget gets its
own chunk.

    from tagger import chunk
    chunks = chunk(records, target_tokens=5000)
"""

import json

TARGET_TOKENS = 5000  # approximate input tokens per request


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def record_tokens(record: dict) -> int:
    """Estimate the token cost of one record as it would be serialized."""
    return estimate_tokens(json.dumps(record, ensure_ascii=False))


def chunk(records: list, target_tokens: int = TARGET_TOKENS) -> list:
    """Greedily pack records into chunks, each ~target_tokens."""
    chunks = []
    current = []
    current_tokens = 0

    for record in records:
        cost = record_tokens(record)
        if current and current_tokens + cost > target_tokens:
            chunks.append(current)
            current = []
            current_tokens = 0
        current.append(record)
        current_tokens += cost

    if current:
        chunks.append(current)

    return chunks
