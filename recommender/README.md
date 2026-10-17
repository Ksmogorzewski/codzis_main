# Recommender (RAG) — Warsaw event recommender

RAG-based event recommender for Warsaw city events. Retrieves candidate events by
**cosine similarity** over local embeddings and optionally re-ranks them with an LLM
(**DeepSeek**) that also explains *why* each event fits the user.

No fine-tuning, no external embedding API, no AWS integration baked in — it's a clean,
importable Python component that the larger system (this repo) can call. It consumes the
target-table events (schema v1, `src/importer/schema.py`) with the `tags` produced by the
[`tagger`](../tagger) pipeline. The AWS side (Lambda, S3 index, API) lives in
[`src/recommender_api`](../src/recommender_api) — see "Rekomendacje (RAG)" in the main README.

## How it works

1. **Chunk** — each event → one embeddable text (`Title. Category1, Category2. Theme, Format. Lead`;
   theme/format are the tagger's taxonomy, the same vocabulary as user interests).
2. **Embed** — local multilingual model `paraphrase-multilingual-mpnet-base-v2` (768-dim),
   running in-process on CPU (no GPU needed).
3. **Index** — in-memory numpy cosine index (top-k via normalized dot product). It can be built
   elsewhere and passed in (`index=`), so serving never re-embeds the events.
4. **Retrieve** — expand the query (optional DeepSeek step: a short/vague request is rewritten
   into a richer Polish search text, cached, with fallback to the raw query), encode the user
   context, apply hard filters (district/cost/mode/audience/price/date), score the filtered
   events on the prebuilt index, add small soft-preference boosts/penalties (`retriever/scoring.py`),
   collapse same-title duplicates and pick a varied top-N.
5. **Rank** (optional) — DeepSeek re-ranks candidates and adds a one-line reason (in Polish)
   per event. Any LLM error falls back to the cosine order.

## Layout

```
recommender/
  __init__.py      # public API: Recommender, recommend()
  chunker/         # event -> embeddable text chunks
  embedder/        # local model + numpy vector index
  retriever/       # filters, query encoder, retrieval, dedupe, soft boosts + variety
  llm/             # DeepSeek client + .env loader (self-contained)
  ranker.py        # DeepSeek re-rank + explanation
```

## Install (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu   # CPU-only torch
pip install -r recommender/requirements.txt
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
| `district` | hard filter, e.g. `"Śródmieście"` (online events pass) |
| `cost` | hard filter: `"Bezpłatne"` / `"Płatne"` / `"Nieznane"` |
| `mode` | hard filter: `"Stacjonarne"` / `"Online"` / `"Hybrydowe"` |
| `audience` | hard filter, e.g. `"Dorośli (18-64)"`: must overlap `tags.audience` (family events always pass) |
| `max_price` | hard filter on a declared price (`attributes.price`) |
| `date_from` / `date_to` | ISO dates `"2026-10-17"`; weekly classes match by weekday |
| `now` | ISO datetime: drops what is already over |
| `themes`, `formats`, `occasion`, `activity_level`, `setting`, `registration`, `accessibility`, `time_of_day`, `home_district`, `near_districts`, `audience`, `mode` | soft preferences (reorder only) |
| `profile` | free-text profile for the LLM ranker |

`recommend(..., min_score=0.30)` — weak matches are **dropped** instead of padding the list,
so a vague query can return fewer than `top_k` good events (better 4 relevant than 10 with 6
noise). Pass `min_score=None` to disable. The floor is applied to the raw cosine, before the
soft-preference boosts, and is model-specific: `DEFAULT_MIN_SCORE` in
`retriever/retriever.py` was calibrated for the mpnet model (relevant pairs 0.38+, irrelevant
pairs 0.42 and below, medians 0.64 vs 0.23) and must be retuned after a model swap.
`rec.last_dropped` reports how many candidates the floor removed.

Hard-filter values may be a single string or a list (any-of). Each `Candidate` carries
`metadata`: `cosine`, `boost`, `matched` (which preferences matched — usable as a reason
without the LLM), `slot` (the first time the user could go) and, after the LLM, `reason`.

## DeepSeek key (optional)

The ranking LLM is optional. Without a key, results are pure cosine ranking. With a key,
DeepSeek re-ranks the top candidates and adds a `reason` to each.

The key is resolved in this order:
1. `DEEPSEEK_API_KEY` environment variable
2. `.env` file (copy `.env.example` → `.env` and fill in)

**Never commit the real `.env`** — it is gitignored.

## Deployment note

This package is deliberately deployment-agnostic: no AWS wiring, no secrets. In this repo it
runs as a **Lambda container image** (`src/recommender_api/Dockerfile`, arm64): model weights
baked into the image, vectors precomputed into an S3 index and refreshed incrementally,
`Recommender(events, model=..., index=...)` built once per container, `.recommend(...)` per
request.

## Notes / limitations

- Embeddings run on CPU; ~1200 events embed in ~2 min on a laptop (mpnet-base, several
  minutes on a small Lambda), so the index is built once and only new texts are embedded
  later. A query is ~0.3–0.6 s including filtering (plus the LLM call when enabled).
- Hard filters on `cost`/`mode`/`audience` read the event's `tags` dict (as produced by the
  `tagger` pipeline into DynamoDB). When a tag is absent, that filter is a no-op; `district`
  and date always apply (schema v1 `district`/`occurrences`/`schedule`, or the raw API's
  `localization`/`occurrence`).
- Same-title events are collapsed after filtering; the kept entry lists all its dates under
  `event["all_dates"]`.
