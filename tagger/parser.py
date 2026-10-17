#!/usr/bin/env python3
"""
Parse and validate the model's multi-dimensional tagging output.

The model is asked to return a JSON object keyed by event id, where each value
is an object with one key per dimension (theme, audience, format, cost, mode).
This module parses that, enforces the closed option lists and max counts, and
collapses single-value dimensions to a plain string.

    from tagger import parse_response
    parsed = parse_response(raw_text, expected_ids)
"""

import json
import re

from .prompt import DIMENSIONS


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_response(
    raw_text: str,
    expected_ids: list[str],
    dimensions: dict | None = None,
) -> dict:
    """
    Validate model output against the expected event ids and dimension schema.

    Returns:
        {
            "results":        {id: {dimension: value}},   # single dims -> str
            "missing_ids":    [ids the model omitted],
            "unknown_values": [(id, dimension, value) dropped as not-allowed],
            "extra_ids":      [ids the model invented],
        }
    """
    dimensions = dimensions or DIMENSIONS

    data = json.loads(_strip_fences(raw_text))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")

    expected_set = set(expected_ids)
    results = {}
    missing = []
    unknown = []  # (id, dimension, value)
    extra = [k for k in data if k not in expected_set]

    for eid in expected_ids:
        if eid not in data:
            missing.append(eid)
            continue

        value = data[eid]
        if not isinstance(value, dict):
            value = {}

        rec = {}
        for dim, spec in dimensions.items():
            raw_vals = value.get(dim, [])
            if raw_vals is None:
                raw_vals = []
            if not isinstance(raw_vals, list):
                raw_vals = [raw_vals]

            cleaned = []
            for tag in raw_vals:
                tag = str(tag)
                if tag in spec["options"]:
                    if tag not in cleaned:
                        cleaned.append(tag)
                else:
                    unknown.append((eid, dim, tag))
            cleaned = cleaned[: spec["max"]]

            if spec["single"]:
                rec[dim] = cleaned[0] if cleaned else None
            else:
                rec[dim] = cleaned

        results[eid] = rec

    return {
        "results": results,
        "missing_ids": missing,
        "unknown_values": unknown,
        "extra_ids": extra,
    }
