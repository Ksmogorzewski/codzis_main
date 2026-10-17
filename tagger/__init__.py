"""Event tagging module — public API."""

from .chunker import chunk
from .client import DeepSeekClient
from .merger import merge
from .orchestrator import Orchestrator
from .parser import parse_response
from .prepare import prepare_records
from .prompt import DIMENSIONS, build_messages

__all__ = [
    "DeepSeekClient",
    "Orchestrator",
    "DIMENSIONS",
    "build_messages",
    "parse_response",
    "chunk",
    "merge",
    "prepare_records",
    "tag_events",
]


def tag_events(
    records: list[dict],
    dimensions: dict | None = None,
    target_tokens: int = 5000,
    api_key: str | None = None,
    output_path=None,
    **client_kwargs,
) -> dict:
    """Tag a list of slim event records via DeepSeek.

    Args:
        records: list of dicts with keys id/title/lead/description/categories.
        dimensions: the dimension schema (defaults to the placeholder DIMENSIONS).
        target_tokens: approx input tokens per chunk.
        api_key: DeepSeek API key (defaults to env var / .env).
        output_path: where to write per-event results (defaults to data/tagged.jsonl).
        client_kwargs: passed to DeepSeekClient (e.g. model=...).

    Returns:
        Orchestrator.run() summary: {"results", "usage", "failures"}.
    """
    client = DeepSeekClient(api_key=api_key, **client_kwargs)
    orchestrator = Orchestrator(
        client=client,
        dimensions=dimensions,
        target_tokens=target_tokens,
        output_path=output_path,
    )
    return orchestrator.run(records)
