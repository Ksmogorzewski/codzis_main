# Recommender (RAG) — Warsaw event recommender

RAG-based event recommender for Warsaw city events. Retrieves candidate events by
**cosine similarity** over local embeddings and optionally re-ranks them with an LLM
(**DeepSeek**) that also explains *why* each event fits the user.

No fine-tuning, no external embedding API, no AWS integration baked in — it's a clean,
importable Python component that the larger system (this repo) can call. It consumes the
`tags` produced by the [`tagger`](../tagger) pipeline.

## How it works

1. **Chunk** — each event → one embeddable text (`Title. Category1, Category2. Lead`).
2. **Embed** — local multilingual model `paraphrase-multilingual-MiniLM-L12-v2` (384-dim),
   running in-process on CPU (no GPU needed).
3. **Index** — in-memory numpy cosine index (top-k via normalized dot product).
4. **Retrieve** — encode the user context, apply hard filters (district/cost/mode/date),
   return top-N candidates. Recurring events (same title, multiple dates) are collapsed.
5. **Rank** (optional) — DeepSeek re-ranks candidates and adds a one-line reason per event.

## Layout

```
recommender/
  __init__.py      # public API: Recommender, recommend()
  chunker/         # event -> embeddable text chunks
  embedder/        # local model + numpy vector index
  retriever/       # filters, query encoder, retrieval, dedupe
  llm/             # DeepSeek client + .env loader (self-contained)
  ranker.py        # DeepSeek re-rank + explanation
```

## Install (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU-only torch
pip install -r requirements.txt
```

## Usage

### As an importable component

```python
from recommender import Recommender

events = [...]                     # your event records (list of dicts)
rec = Recommender(events)          # build once (loads model + index)

user = {
    "query": "darmowy koncert w weekend",
    "interests": ["Muzyka", "Czas wolny"],
    "district": "Śródmieście",
    "cost": "Bezpłatne",
    "date_from": "2026-10-17",
    "date_to": "2026-10-19",
}

results = rec.recommend(user, top_k=10)        # list[Candidate], ranked best-first
for c in results:
    print(c.score, c.event["title"], c.metadata.get("reason"))
```

`user` (a.k.a. `user_context`) is a flexible dict — all fields optional:

| field | meaning |
|---|---|
| `query` | natural-language request |
| `interests` | list of category strings |
| `liked_event_ids` | past taste (ids of liked events) |
| `district` | hard filter, e.g. `"Śródmieście"` |
| `cost` | hard filter: `"Bezpłatne"` / `"Płatne"` / `"Nieznane"` |
| `mode` | hard filter: `"Stacjonarne"` / `"Online"` / `"Hybrydowe"` |
| `audience` | hard filter, e.g. `"Dorośli (18-64)"` |
| `date_from` / `date_to` | ISO dates `"2026-10-17"` |

## DeepSeek key (optional)

The ranking LLM is optional. Without a key, results are pure cosine ranking. With a key,
DeepSeek re-ranks the top candidates and adds a `reason` to each.

The key is resolved in this order:
1. `DEEPSEEK_API_KEY` environment variable
2. `.env` file (copy `.env.example` → `.env` and fill in)

**Never commit the real `.env`** — it is gitignored.

## Deployment note

This package is deliberately deployment-agnostic: no AWS wiring, no secrets. The intended
pattern is a **Docker container on EC2/ECS** (`python:3.13-slim` base): bake the model
weights into the image, instantiate `Recommender(events)` once at startup, and call
`.recommend(...)` per request.

## Notes / limitations

- Embeddings run on CPU; at ~500 events the index builds in seconds and each query is ~20–30 ms.
- Hard filters on `cost`/`mode`/`audience` read the event's `tags` dict (a `{cost, mode,
  audience, ...}` map, as produced by the `tagger` pipeline into DynamoDB). When `tags` is
  absent, those filters are no-ops; `district` (via `localization`) and date (via
  `occurrence`) always apply.
- Recurring events are collapsed by normalized title; the kept entry lists all its dates
  under `event["all_dates"]`.
