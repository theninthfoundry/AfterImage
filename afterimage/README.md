# Afterimage

**An incident-response agent that remembers.**

Every incident becomes experience for the next one. Afterimage is a real FastAPI
service that runs a deterministic incident simulation through an agent loop —
observe, recall, reason, investigate, decide, verify, reflect, remember —
where **recall** and **remember** are live calls to
[Hindsight](https://hindsight.vectorize.io), not a local cache. Built for the
HackwithHyderabad 3.0 problem statement.

## What changed since the first pass

The first version worked but had three real gaps: every incident shared the
same root cause (so "learning" only ever demonstrated one story), there was no
structured record of what actually happened independent of Hindsight, and there
was no way to see memory as a graph or a timeline. This version closes those:

- **Five scenarios, four distinct root-cause families** — not variations of
  one story. `payment-api`/`orders-api` share a deployment-regression family
  (the recurring-pattern demo); `auth-service` (Redis eviction) and
  `api-gateway` (rate-limiter misconfiguration) are unrelated failures with
  their own hypothesis sets, used to prove memory does **not** leak across
  incidents that don't match (`test_unrelated_incident_not_influenced_by_memory`).
- **A structured audit trail** (`app/db.py`, SQLAlchemy, SQLite by default,
  Postgres via `DATABASE_URL`) recording every run and every stage —
  independent of Hindsight. This is the Postgres-for-facts /
  Hindsight-for-experience split the brief asks for, actually implemented
  rather than left as a limitation.
- **A memory graph and a real timeline** (`/api/graph`, `/api/runs`), built
  entirely from that audit trail, so they render even when Hindsight is
  offline.
- **Expandable "why this memory"** in the UI — click a recalled fact to see
  its full text and matched signals, not just a relevance percentage.

## Problem

The problem statement asks for an agent that uses Hindsight's persistent
memory to learn, recall context, and improve across interactions — not a
stateless chatbot, and not Hindsight used as a vector store for documents.

## Core insight

Most "AI + memory" demos store answers. The more useful thing to remember in
incident response is what **didn't** work: a hypothesis that looked plausible
and was ruled out. Afterimage's memory is built from incident, investigation,
resolution, and pattern facts — and it's the investigation facts (what was
ruled out, and why) that actually reorder the agent's hypotheses on the next
matching incident.

## Architecture

```
        SIMULATED PRODUCTION (5 scenarios, app/sim.py, deterministic)
                              │
                              ▼
                   AGENT LOOP (app/agent.py)
      observe → recall → reason → investigate → decide
                              │                       │
                 recall/retain via Hindsight    verify → reflect (LLM optional)
                              │                       │
                              ▼                       ▼
                  app/memory.py → Hindsight       remember → Hindsight
                     (experience: what was              │
                    ruled out, what worked)              ▼
                              │                app/db.py → SQLite/Postgres
                              │                (structured audit trail:
                              │                 every run, every stage,
                              │                 independent of Hindsight)
                              ▼                       │
                     NEXT INCIDENT,          /api/graph, /api/runs
                     better recall           (built from the audit trail,
                                              work even Hindsight-offline)
```

FastAPI serves both the JSON API and the static frontend (`static/index.html`,
plain HTML/CSS/JS, no build step, no framework).

## Hindsight integration

`app/memory.py` wraps the official `hindsight-client` Python SDK. There is
**no local fallback store**. If Hindsight is unreachable, every call raises
`MemoryOffline`, and the agent and API report `"memory": "offline"` instead of
silently degrading to fake data.

- `retain(content, metadata, document_id)` — one fact per incident, per
  ruled-out hypothesis, per resolution, and (from the second matching
  incident in a family onward) one pattern fact.
- `recall(query)` — a natural-language query built from the current
  incident's service and signals, asking specifically what was ruled out and
  what the fix was.
- Each retained fact carries structured `metadata` (`kind`, `hypothesis`,
  `result`, `signals`) so recall is interpreted deterministically. A
  Jaccard-similarity threshold (0.3) on `signals` filters out memories from
  an unrelated incident family before they can influence ranking — this is
  what `test_unrelated_incident_not_influenced_by_memory` checks.
- If Hindsight returns a fact without that metadata, the agent falls back to
  parsing the fact text for known hypothesis names (`recall_context`'s
  text-fallback path) — flagged under Limitations, since it's simple keyword
  matching, not independently unit tested.

## The five scenarios

| Incident | Service | Root cause family | Confirmed cause |
|---|---|---|---|
| INC-001 | payment-api | deployment regression | pool exhaustion, v3.4.2 |
| INC-002 | payment-api | deployment regression | pool exhaustion, v3.5.0 |
| INC-003 | orders-api | deployment regression | pool exhaustion, v1.9.3 |
| INC-004 | auth-service | — (standalone) | Redis eviction thrashing |
| INC-005 | api-gateway | — (standalone) | rate-limiter misconfiguration |

INC-001→002→003 is the recurring-pattern story: run 001, then 002 recalls
what was ruled out and promotes the right hypothesis immediately, and 003
shows the same pattern generalising to a different service. INC-004/005 have
no repeat partner in this build — running them shows the baseline path, and
proves memory from the payment-api family doesn't wrongly apply to them.

## Agent architecture

Single orchestrator (`app/agent.py:run_incident`), with distinct
responsibilities as functions rather than six separate services:

| Role | Function | Output |
|---|---|---|
| Observer | `run_incident` (observe step) | symptom summary |
| Historian | `recall_context` | relevant past facts, each with matched signals |
| Investigator | `rank` | re-ordered hypothesis list with scores, per incident |
| Evidence | each incident's own `hyp` dict + the investigate loop | per-hypothesis test result |
| Decision | `run_incident` (decide step) | root cause + action |
| Memory Writer | `candidates` + `make_lesson` | importance-filtered facts, one LLM-or-template lesson |

## Memory model

Every `retain` call stores one fact with `metadata.kind` of `incident`,
`investigation`, `resolution`, or `pattern` (written once two incidents in
the same family confirm the same root cause). Routine telemetry and
duplicate-log candidates are generated too, scored `importance < 0.5`, and
dropped before any `retain` call — a real filter, not just a comment
(`test_low_importance_is_dropped`).

## Structured audit trail (new)

`app/db.py` is deliberately separate from Hindsight. It records, per run: the
incident, service, root cause, fix, diagnosis time, wrong-hypothesis count,
memory status, and every stage with its timing — independent of whether
Hindsight was reachable. `/api/runs` returns this as a real timeline (actual
timestamps, not simulated ones). `/api/graph` builds a node/edge graph
(incident → service, incident → root cause, root cause → resolution, and
`similar_to` edges between incidents sharing a root cause) purely from this
table, so the Graph tab works even with Hindsight offline.

## Demo

1. Pick **INC-001** — payment-api, empty memory, 4 hypotheses tested, 3 wrong.
2. Pick **INC-002** — same family, different deploy. Recall returns the
   ruled-out hypotheses from INC-001; `deployment regression` is promoted to
   first; 0 wrong hypotheses.
3. Pick **INC-004** or **INC-005** — a genuinely different incident. Memory
   from the payment-api family does not apply; the agent runs its own prior
   order.
4. **Results** tab — `/api/benchmark` runs the deployment-regression family
   twice (no memory, then a temporary Hindsight bank) and reports the
   measured seconds/hypothesis counts.
5. **Graph** tab — the real timeline and memory graph of everything you just
   ran, from the structured audit trail.

"play the demo" runs steps 1–2 automatically. Every stage in the UI comes
from a real API response; nothing is a canned animation.

## Evaluation methodology

`/api/benchmark`:

1. creates a throwaway Hindsight bank (`{bank}-bench-<uuid>`) so it never
   pollutes your main memory,
2. runs the deployment-regression family against `mem=None` (baseline, agent
   skips recall/remember entirely — `test_baseline_never_touches_memory`),
3. runs the same three against the fresh bank with real recall/retain,
4. deletes the temporary bank,
5. returns per-incident `sec`, `tested`, `wrong`, `recalled` for both runs.

`tests/test_agent.py` (11 tests) covers: memory changing investigation order
end to end, baseline never touching memory, offline being reported not
faked, low-value facts being dropped, LLM failure degrading to a templated
lesson without losing the run, pattern generalising across services, memory
from one incident family not influencing an unrelated one, all five
scenarios resolving to their own declared root cause, `/api/health`
correctly reporting offline, a run being persisted to the structured audit
trail with its full stage list, and the graph linking incidents that share a
root cause.

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
| `DATABASE_URL` | no | defaults to a local SQLite file; point at Postgres for anything beyond a demo |
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

`docker-compose.yml` runs the app against a real Postgres container:

```bash
docker compose up --build
```

Or standalone with the included `Dockerfile` (SQLite by default, or set
`DATABASE_URL` to your own Postgres). Set the environment variables above in
your host's secret manager — never commit `.env`.

## Limitations

- Incident telemetry is a fixed, deterministic simulation (`app/sim.py`) —
  five scenarios, not live infrastructure. The UI and this README say so
  throughout.
- The text-based metadata-fallback parser in `recall_context` (for facts
  ingested without Afterimage's own metadata) is simple keyword matching, not
  independently unit tested — flagged here rather than hidden.
- Not tested against a live Hindsight or Groq endpoint from the environment
  this was built in (no network access to either from there); tested against
  the real `hindsight-client` SDK's interface using test doubles, plus a real
  unreachable-host case that exercises the genuine network/error path. Run
  `pytest -q` and check `/api/health` against your own credentials before
  relying on it.
- The memory graph's layout is a simple fixed-row placement (service /
  incident / root cause / resolution), not a force-directed layout — fine at
  demo scale (a handful of runs), not built to stay readable at hundreds.

## Future work

- Live telemetry connectors (Prometheus/OpenTelemetry/CloudWatch) in place of
  `app/sim.py`.
- Human-in-the-loop remediation approval (Slack/PagerDuty) before a rollback
  action is "executed."
- A confidence score surfaced per pattern fact, computed from how many times
  it's been confirmed vs. contradicted.
- More scenario families beyond the two currently modelled.
