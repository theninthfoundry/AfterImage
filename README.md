# Afterimage

**An incident-response agent that remembers.**

Every incident becomes experience for the next one. Afterimage is a small, real
FastAPI service that runs a deterministic incident simulation through an agent
loop — observe, recall, reason, investigate, decide, verify, reflect, remember —
where the **recall** and **remember** steps are live calls to
[Hindsight](https://hindsight.vectorize.io), not a local cache. Built for the
HackwithHyderabad 3.0 problem statement.

## Problem

The problem statement asks for an agent that uses Hindsight's persistent memory
to learn, recall context, and improve across interactions — not a stateless
chatbot, and not Hindsight used as a vector store for documents.

## Core insight

Most "AI + memory" demos store answers. The more useful thing to remember in
incident response is what **didn't** work: a hypothesis that looked plausible
and was ruled out. Afterimage's memory is built from three kinds of fact —
what happened, what was ruled out, and what pattern repeats across incidents —
and the second kind is what actually reorders the agent's investigation on the
next incident.

## Why persistent memory matters here

Without memory, every incident is investigated from a fixed prior order of
hypotheses. With memory, a hypothesis that was previously confirmed as root
cause for a matching incident gets boosted, and one that was ruled out gets
suppressed — before any evidence is even tested. That's a measurable
difference (see `/api/benchmark`), not a UI trick.

## Architecture

```
        SIMULATED PRODUCTION (deterministic, labelled simulated)
                         │
                         ▼
                  INCIDENT (app/sim.py)
                         │
                         ▼
              AGENT LOOP (app/agent.py)
     observe → recall → reason → investigate → decide
                         │
             recall / retain via Hindsight
                         │
                         ▼
                app/memory.py → Hindsight Cloud
                         │
                         ▼
        verify → reflect (optional LLM) → remember
                         │
                         ▼
               new facts retained in Hindsight
                         │
                         ▼
                  NEXT INCIDENT, better recall
```

FastAPI serves both the JSON API and the static frontend (`static/index.html`,
plain HTML/CSS/JS, no build step, no framework).

## Hindsight integration

`app/memory.py` wraps the official `hindsight-client` Python SDK. There is
**no local fallback store**. If Hindsight is unreachable, every call raises
`MemoryOffline`, and the agent and API report `"memory": "offline"` instead of
silently degrading to fake data — this satisfies the "no fake features" rule
in the brief.

- `retain(content, metadata, document_id)` — writes one fact per incident,
  per ruled-out hypothesis, per resolution, and (from the second matching
  incident onward) one pattern fact.
- `recall(query)` — a natural-language query built from the current
  incident's service and signals, asking specifically what was ruled out and
  what the fix was. Hindsight's own relevance/budgeting decides what comes
  back; Afterimage does not pre-filter by embedding similarity itself.
- Each retained fact carries structured `metadata` (`kind`, `hypothesis`,
  `result`, `signals`) so recall can be interpreted deterministically. If
  Hindsight returns a fact without that metadata (e.g. ingested from
  elsewhere), the agent falls back to parsing the fact text for known
  hypothesis names — this path is exercised in `test_agent.py` implicitly
  through the metadata-present path; see Limitations.

## Agent architecture

Single orchestrator (`app/agent.py:run_incident`), not six separate network
services — appropriate for a hackathon slice, matching the brief's
"specialized roles" as functions with distinct responsibilities:

| Role | Function | Output |
|---|---|---|
| Observer | `run_incident` (observe step) | symptom summary |
| Historian | `recall_context` | relevant past facts, each with matched signals |
| Investigator | `rank` | re-ordered hypothesis list with scores |
| Evidence | `sim.HYP` + the investigate loop | per-hypothesis test result |
| Decision | `run_incident` (decide step) | root cause + action |
| Memory Writer | `candidates` + `make_lesson` | importance-filtered facts, one LLM-or-template lesson |

## Memory model

Every `retain` call stores one fact with `metadata.kind` of:

- `incident` — service, root cause, fix, recovery time
- `investigation` — a hypothesis and why it was ruled out or only partly true
- `resolution` — what fixed it and how long recovery took
- `pattern` — written only once two incidents share a confirmed root cause;
  generalises across services (see `test_pattern_generalises_to_other_service`)

Routine telemetry and duplicate log candidates are generated too, scored
`importance < 0.5`, and dropped before any `retain` call — the importance
filter the brief asks for, not just a comment.

## Demo

1. `Run INC-001` — payment-api, empty memory, 4 hypotheses tested, 3 wrong.
2. `Run INC-002` — same service, different deploy. Recall returns the ruled-out
   hypotheses from INC-001; `deployment regression` is promoted to first;
   0 wrong hypotheses.
3. **Results** tab — `/api/benchmark` runs both incidents twice, once against
   no memory and once against a temporary, freshly-created Hindsight bank,
   and reports the actual measured seconds/hypothesis counts, not fixed
   numbers.

"play the demo" runs this sequence automatically. Every stage in the UI comes
from a real API response; nothing is a canned animation.

## Evaluation methodology

`/api/benchmark` is the stateless-vs-memory experiment from the brief. It:

1. creates a throwaway Hindsight bank (`{bank}-bench-<uuid>`) so it never
   pollutes your main memory,
2. runs INC-001–003 against `mem=None` (baseline, agent skips recall/remember
   entirely — see `test_baseline_never_touches_memory`),
3. runs the same three against the fresh bank with real recall/retain,
4. deletes the temporary bank,
5. returns per-incident `sec`, `tested`, `wrong`, `recalled` for both runs.

`tests/test_agent.py` covers: memory changing investigation order end to end,
baseline never touching memory, offline being reported not faked, low-value
facts being dropped, LLM failure degrading to a templated lesson without
losing the run, pattern generalising across services, and `/api/health`
correctly reporting offline when Hindsight can't be reached.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in HINDSIGHT_URL / HINDSIGHT_API_KEY
```

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `HINDSIGHT_URL` | yes | Hindsight Cloud endpoint, or your self-hosted URL |
| `HINDSIGHT_API_KEY` | yes for Cloud | promo code `MEMHACK99` gives $50 credit |
| `HINDSIGHT_BANK` | no | defaults to `afterimage` |
| `GROQ_API_KEY` | no | without it, pattern "lessons" are templated, clearly labelled in the UI |
| `GROQ_MODEL` | no | defaults to `openai/gpt-oss-120b` |

## Local development

```bash
uvicorn app.main:app --reload
# open http://localhost:8000
```

```bash
pytest -q
```

## Deployment

Any container host that can run Python works. Minimal `Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Set the environment variables above in your host's secret manager — never
commit `.env`.

## Limitations

- Incident telemetry is a fixed, deterministic simulation
  (`app/sim.py`) — three scenarios, not live infrastructure. The UI and this
  README say so throughout.
- No PostgreSQL layer yet: incident state lives only in the API response for
  the run that produced it, not persisted structured application data
  separate from Hindsight. For a hackathon-scale slice this was traded for a
  working, tested Hindsight integration; see Future work.
- The text-based metadata-fallback parser in `recall_context` (for facts
  ingested without Afterimage's own metadata) is simple keyword matching, not
  independently unit tested — flagged here rather than hidden.
- Not tested against a live Hindsight or Groq endpoint from this environment
  (the sandbox that built this had no network access to either); tested
  against the real `hindsight-client` SDK's interface using fakes, plus a
  real unreachable-host case that exercises the genuine network/error path.
  Run `pytest -q` and `/api/health` against your own credentials before
  relying on it.

## Future work

- PostgreSQL for structured incident/service state, matching the brief's
  Postgres-for-facts / Hindsight-for-experience split more fully.
- Memory graph and memory timeline views.
- More than three scenarios; a memory confidence score surfaced per pattern.
- A "why this memory" expansion per recalled fact in the UI.
