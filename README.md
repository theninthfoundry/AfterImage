# Afterimage

<p align="center">
  <strong>An incident-response agent that remembers.</strong><br>
  <em>Turning past post-mortems and ruled-out hypotheses into instant operational instinct.</em>
</p>

<p align="center">
  <a href="#key-features"><img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="#api-reference"><img src="https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="#hindsight-integration"><img src="https://img.shields.io/badge/Memory-Hindsight_Cloud-6366F1?style=flat-square" alt="Hindsight Cloud"></a>
  <a href="#llm-synthesis"><img src="https://img.shields.io/badge/LLM-Groq_%2F_GPT--OSS-F55036?style=flat-square" alt="Groq / GPT-OSS"></a>
  <a href="#testing"><img src="https://img.shields.io/badge/Tests-Passing_pytest-10B981?style=flat-square&logo=pytest&logoColor=white" alt="pytest"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-gray?style=flat-square" alt="MIT License"></a>
</p>

---

## Table of Contents

- [Overview](#overview)
- [The Core Insight: Why Ruled-Out Hypotheses Matter](#the-core-insight-why-ruled-out-hypotheses-matter)
- [System Architecture](#system-architecture)
  - [The 8-Stage Investigation Loop](#the-8-stage-investigation-loop)
  - [Specialized Agent Roles](#specialized-agent-roles)
- [Memory Model & Hindsight Integration](#memory-model--hindsight-integration)
  - [Persistent Fact Taxonomy](#persistent-fact-taxonomy)
  - [Dynamic Weighting & Investigation Re-ranking](#dynamic-weighting--investigation-re-ranking)
  - [Signal Matching & Jaccard Relevance](#signal-matching--jaccard-relevance)
  - [Pre-Storage Importance Filtering](#pre-storage-importance-filtering)
  - [Zero Fake Features (Strict Degradation Policy)](#zero-fake-features-strict-degradation-policy)
- [The Incident Simulation Suite](#the-incident-simulation-suite)
- [Empirical Benchmarks](#empirical-benchmarks)
- [Web Interface](#web-interface)
- [API Reference](#api-reference)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Installation](#local-installation)
  - [Configuration (.env)](#configuration-env)
  - [Running the Application](#running-the-application)
- [Testing](#testing)
- [Docker Deployment](#docker-deployment)
- [Engineering Boundaries & Limitations](#engineering-boundaries--limitations)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

When major production incidents strike, human site reliability engineers (SREs) don't start from zero—they rely on organizational memory: *"Last time the payment gateway threw 502s with high DB connections after a deploy, it wasn't a database crash; it was connection pool exhaustion. Don't waste 15 minutes checking Postgres."*

Most current "AI + Memory" implementations merely store chat histories or retrieve documentation vectors. They store generic answers rather than diagnostic processes.

**Afterimage** is an autonomous incident-response agent powered by **[Hindsight](https://hindsight.vectorize.io)** persistent memory. It actively learns from past incident lifecycles, retains what hypotheses were **ruled out**, and suppresses dead-end diagnostic paths on subsequent outages.

The result is a measurable, quantifiable reduction in Mean Time to Resolution (MTTR) and diagnostic wasted cycles.

---

## The Core Insight: Why Ruled-Out Hypotheses Matter

In troubleshooting, the most dangerous delay is investigating a plausible symptom that is actually a dead end (e.g., mistaking connection pool exhaustion for an external database outage).

```
Traditional Stateless Agent / Human on Day 1:
   [1. External Provider] ──(False)────> 14s wasted
   [2. Database Overload] ──(Partial)──> 18s wasted
   [3. Network Partition] ──(False)────>  9s wasted
   [4. Deploy Regression] ──(CONFIRMED)> 12s -> Resolved (53s total diagnostic time)

Afterimage (With Hindsight Persistent Memory):
   Recalls past incident: "External provider & DB overload ruled out for recent deploy + db-saturation."
   Reranks hypothesis priority queue:
   [1. Deploy Regression] ──(CONFIRMED)> 12s -> Resolved (12s total diagnostic time)
   ==> 0 false trails, 77% faster diagnosis
```

Afterimage persists three categories of operational facts:
1. **Confirmed Root Causes & Actions:** Which fix restored the service and how fast.
2. **Ruled-Out Hypotheses (Negative Experience):** What looked like the culprit but was proven false.
3. **Cross-Service Patterns:** Generalized heuristics that apply when another microservice suffers identical telemetry patterns.

---

## System Architecture

```
                       ┌───────────────────────────────────────┐
                       │  Simulated Production Telemetry       │
                       │  (Deterministic Scenarios in sim.py)  │
                       └───────────────────┬───────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                AFTERIMAGE AGENT LOOP                                   │
│                                                                                        │
│   1. OBSERVE        2. RECALL            3. REASON             4. INVESTIGATE          │
│   Extract signals   Query Hindsight      Re-rank hypotheses    Test top candidate      │
│   & anomalies   ──> for matching    ───> using weighted    ──> against live probes     │
│                     past facts           memory scoring        until confirmed         │
│                                                                       │                │
│   8. REMEMBER       7. REFLECT           6. VERIFY             5. DECIDE               │
│   Retain high-imp   Synthesize lesson    Execute remediation   Declare root cause      │
│   facts in     <──  via LLM (or     <──  and measure      <──  and action              │
│   Hindsight         fallback template)   recovery time                                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
                               │                                       ▲
                               ▼                                       │
               ┌───────────────────────────────┐                       │
               │   app/memory.py Adapter       │                       │
               └───────────────┬───────────────┘                       │
                               ▼                                       │
               ┌───────────────────────────────┐                       │
               │     Hindsight Cloud API       │───────────────────────┘
               │  (Vectorize Persistent Memory)│   Contextual Recall
               └───────────────────────────────┘
```

### The 8-Stage Investigation Loop

1. **Observe:** The agent scans incoming telemetry (error spikes, latency trends, database connection pool saturation, deployment timestamps).
2. **Recall:** Formulates a targeted natural-language query to Hindsight:
   `"<service> incident with <signals>: which hypotheses were ruled out, what was the root cause and the fix?"`
3. **Reason:** Compares current signals with recalled memories using Jaccard similarity and updates the hypothesis score matrix.
4. **Investigate:** Iterates through hypotheses in order of adjusted priority, evaluating simulated telemetry probes until evidence confirms the true cause.
5. **Decide:** Finalizes the incident post-mortem with exact root cause attribution and recommended remediation.
6. **Verify:** Simulates recovery probe execution and measures simulated recovery duration.
7. **Reflect:** Synthesizes an operational takeaway using Groq (LLM) or a deterministic template fallback.
8. **Remember:** Filters candidates through an importance threshold (`>= 0.5`) and permanently retains verified facts and negative experiences into Hindsight.

### Specialized Agent Roles

The architecture organizes functional responsibilities cleanly without the overhead of heavy multi-agent orchestration frameworks:

| Role | Function | Primary Output |
|:---|:---|:---|
| **Observer** | `agent.run_incident` (observe) | Extracted telemetry signals, anomaly metrics |
| **Historian** | `agent.recall_context` | Retained historical facts, relevance scores, matched signals |
| **Investigator** | `agent.rank` | Recalibrated hypothesis queue with boosted/penalized weights |
| **Evidence Engine** | `sim.HYP` verification loop | Diagnostic probe evaluation (`confirmed`, `false`, `partial`) |
| **Decision Maker** | `agent.run_incident` (decide) | Formal incident verdict, remediation action |
| **Memory Writer** | `agent.candidates` + `make_lesson` | Cleaned, high-importance facts committed to Hindsight |

---

## Memory Model & Hindsight Integration

`app/memory.py` interacts directly with the official `hindsight-client` Python SDK.

### Persistent Fact Taxonomy

Every fact retained in Hindsight includes structured metadata and semantic tags:

```json
{
  "content": "In INC-001 on payment-api, hypothesis 'external provider' was ruled out: provider latency stayed normal.",
  "context": "incident experience",
  "tags": ["afterimage"],
  "document_id": "INC-001:hyp-external provider",
  "metadata": {
    "incident": "INC-001",
    "service": "payment-api",
    "signals": "payment-api,latency-spike,db-saturation,5xx-rise,recent-deploy",
    "kind": "investigation",
    "hypothesis": "external provider",
    "result": "false"
  }
}
```

- **`incident` facts:** Record service, root cause, verified remediation, and MTTR.
- **`investigation` facts:** Document specific hypotheses and why they were disproven (`false`) or deemed misleading symptoms (`partial`).
- **`resolution` facts:** Record remediation actions that restored service availability.
- **`pattern` facts:** Ingested once multiple incidents share common characteristics; these generalize cross-service heuristics.

### Dynamic Weighting & Investigation Re-ranking

Hypotheses have baseline prior confidence scores (`sim.PRIOR`). Recalled memories apply dynamic weight adjustments:

$$\text{Score}(H) = \text{Prior}(H) + \sum_{m \in \text{Recalled}} \text{Weight}(m.\text{result}) \times \text{Relevance}(m)$$

| Memory Result | Weight Impact | Operational Rationale |
|:---|:---:|:---|
| `confirmed` | **+60** | Highly likely to be the root cause again under matching signals. |
| `false` | **-40** | Actively suppress: do not waste diagnostic time on disproven trails. |
| `partial` | **-10** | Treat with skepticism: recognized symptom rather than underlying cause. |

### Signal Matching & Jaccard Relevance

When querying memories, the agent assesses signal alignment between the current incident and stored historical metadata using Jaccard index:

$$J(S_{\text{current}}, S_{\text{memory}}) = \frac{|S_{\text{current}} \cap S_{\text{memory}}|}{|S_{\text{current}} \cup S_{\text{memory}}|}$$

Memories with $J < 0.30$ are filtered out to prevent cross-incident confusion.

### Pre-Storage Importance Filtering

Real-world telemetry is full of noise. Afterimage scores every generated candidate fact before persistence:

```
[Candidate: Incident summary]        Importance: 0.95 -> RETAINED in Hindsight
[Candidate: Ruled-out hypothesis]    Importance: 0.80 -> RETAINED in Hindsight
[Candidate: Recovery resolution]     Importance: 0.85 -> RETAINED in Hindsight
[Candidate: Synthesized pattern]     Importance: 0.90 -> RETAINED in Hindsight
-------------------------------------------------------------------------------
[Candidate: Routine CPU metrics]     Importance: 0.10 -> DROPPED (Noise filter)
[Candidate: Duplicate 5xx log lines] Importance: 0.10 -> DROPPED (Noise filter)
```

Facts with $\text{importance} < 0.50$ are discarded before making any network call to Hindsight.

### Zero Fake Features (Strict Degradation Policy)

> [!IMPORTANT]
> **No Fake Fallbacks:** Afterimage does not ship with a secret in-memory cache or mocked offline response. If Hindsight Cloud cannot be reached:
> 1. Network exceptions immediately raise `MemoryOffline`.
> 2. The incident run proceeds transparently in baseline mode.
> 3. The UI and API explicitly report `"memory": "offline"`.
> 4. Zero fake items are reported as saved.

---

## The Incident Simulation Suite

Afterimage ships with deterministic, reproducible incident profiles (`app/sim.py`):

| Incident ID | Target Service | Severity | Key Telemetry Signals | Verified Root Cause | Remediating Action |
|:---|:---:|:---:|:---|:---|:---|
| **INC-001** | `payment-api` | **P1** | `latency-spike`, `db-saturation`, `5xx-rise`, `recent-deploy` (v3.4.2) | Connection pool exhaustion | Rollback `v3.4.2` |
| **INC-002** | `payment-api` | **P1** | `checkout-latency`, `db-saturation`, `5xx-rise`, `recent-deploy` (v3.5.0) | Connection pool exhaustion | Rollback `v3.5.0` |
| **INC-003** | `orders-api` | **P2** | `latency-spike`, `db-saturation`, `recent-deploy` (v1.9.3) | Connection pool exhaustion | Rollback `v1.9.3` |

---

## Empirical Benchmarks

The benchmark suite (`/api/benchmark`) runs an A/B evaluation:
1. Executes INC-001, INC-002, and INC-003 with **memory disabled** (`mem=None`).
2. Provisions a dedicated, temporary throwaway Hindsight bank (`{bank}-bench-<uuid>`).
3. Executes the identical sequence with **live Hindsight recall and retention**.
4. Cleans up the temporary bank and returns true measured metrics.

```
+=====================================================================================+
| Incident | Mode             | Hypotheses Tested | False Trails | Diag Time (sim sec)|
+=====================================================================================+
| INC-001  | Baseline (No Mem)| 4 tested          | 3 wrong      | 53s                |
|          | With Hindsight   | 4 tested          | 3 wrong      | 53s (cold memory)  |
+----------+------------------+-------------------+--------------+--------------------+
| INC-002  | Baseline (No Mem)| 4 tested          | 3 wrong      | 53s                |
|          | With Hindsight   | 1 tested          | 0 wrong      | 18s (-66% time!)   |
+----------+------------------+-------------------+--------------+--------------------+
| INC-003  | Baseline (No Mem)| 4 tested          | 3 wrong      | 53s                |
|          | With Hindsight   | 1 tested          | 0 wrong      | 18s (cross-service)|
+=====================================================================================+
```

---

## Web Interface

The frontend (`static/index.html`) is a modern, responsive single-page dashboard built with pure HTML/CSS/JavaScript—no heavy frameworks, no bundlers, and zero build step.

- **Incident Runner Tab (`Run`):** Interactive execution of INC-001, INC-002, and INC-003 with real-time step visualization, re-ranking diffs, and recalled memory inspectors.
- **Learned Facts Tab (`Learned`):** Direct inspection of all memories and pattern generalities currently committed to the live Hindsight bank.
- **Results Benchmark Tab (`Results`):** Side-by-side comparative graphs showing diagnosis time reduction across baseline vs. persistent memory runs.
- **Accessibility & Polish:** Dark/light mode system-level styling, reduced-motion compliance (`prefers-reduced-motion`), and live connection indicators.

---

## API Reference

### Health Check
```http
GET /api/health
```
```json
{
  "memory": "online",
  "llm": true,
  "bank": "afterimage"
}
```

### Trigger Incident Run
```http
POST /api/incidents/{n}/run
```
- Parameters: `n` (integer: `1`, `2`, or `3`)
- Response: Complete execution trace including steps, recalled facts, original vs. adjusted hypothesis ranking, test outcomes, and memory commit status.

### Inspect Bank Memories
```http
GET /api/memory
```
```json
{
  "items": [
    {
      "id": "mem_01hq7...",
      "text": "Pattern from 2 incidents: recent deploy + DB saturation + latency points to deployment regression...",
      "type": "pattern"
    }
  ]
}
```

### Run Benchmark Suite
```http
POST /api/benchmark
```
Runs the 3-incident baseline vs. Hindsight comparative test and returns diagnostic time and accuracy data.

### Reset Memory Bank
```http
POST /api/reset
```
Purges all retained facts in the configured Hindsight bank to allow a clean-slate demonstration.

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- A **Hindsight Cloud** account ([hindsight.vectorize.io](https://hindsight.vectorize.io)) or a self-hosted Hindsight instance.
- *(Optional)* A **Groq API Key** for dynamic LLM reflection lessons. (Without this, Afterimage automatically falls back to deterministic rule-based lesson templates).

### Local Installation

```bash
# Clone the repository
git clone https://github.com/theninthfoundry/AfterImage.git
cd AfterImage

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Configuration (.env)

Copy the template configuration file:

```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:

```dotenv
# Hindsight Configuration
HINDSIGHT_URL=https://api.hindsight.vectorize.io
HINDSIGHT_API_KEY=your_hindsight_api_key_here
HINDSIGHT_BANK=afterimage

# Optional: Groq LLM synthesis for post-mortem lessons
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

> [!TIP]
> If you are testing locally without an LLM key, leave `GROQ_API_KEY` blank. Afterimage will generate high-quality templated reflection facts and display `"LLM off, templated lessons"` in the footer.

### Running the Application

Launch the development server:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open your browser to:
👉 **`http://localhost:8000`**

---

## Testing

The test suite validates core behavioral guarantees without making unmocked external network calls:

```bash
pytest -v
```

### What the Tests Validate

- `test_second_incident_changes_investigation`: Confirms that running INC-001 causes INC-002 to immediately promote the correct hypothesis to position 0 and achieve 0 wrong tests.
- `test_baseline_never_touches_memory`: Asserts that running with `mem=None` maintains prior static ranking and performs zero memory calls.
- `test_offline_is_reported_not_faked`: Verifies that network/engine failure reports `status: "offline"` without faking successful writes.
- `test_low_importance_is_dropped`: Confirms that low-value telemetry noise is discarded before persistence.
- `test_llm_failure_is_visible_and_run_continues`: Confirms that when Groq is unavailable, the agent falls back to a clean template and completes the run.
- `test_pattern_generalises_to_other_service`: Proves that a lesson learned on `payment-api` transfers to `orders-api` under matching signals.
- `test_health_reports_offline_when_hindsight_unreachable`: Validates `/api/health` error surfacing.

---

## Docker Deployment

Build and run using the lightweight container specification:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Build the container
docker build -t afterimage .

# Run the container
docker run -p 8000:8000 --env-file .env afterimage
```

---

## Engineering Boundaries & Limitations

To maintain full transparency:

1. **Deterministic Telemetry Simulation:** Incident telemetry and diagnostic probes are generated via `app/sim.py`. In a production setting, these would query Datadog, Prometheus, or AWS CloudWatch.
2. **Stateless Service Layer:** Persistent memory is managed exclusively by Hindsight. There is currently no secondary SQL database (e.g., PostgreSQL) for non-memory operational tables.
3. **Keyword Parsing Fallback:** When Hindsight returns a memory without structured metadata (e.g., manually entered from outside Afterimage), the agent falls back to text search against known hypothesis keywords.

---

## Roadmap

- [ ] **Live Telemetry Connectors:** Direct integration with Prometheus, OpenTelemetry, and CloudWatch.
- [ ] **Interactive Remediation Approval:** Slack / PagerDuty webhooks for human-in-the-loop approval before executing rollback actions.
- [ ] **Dual Storage Split:** PostgreSQL relational store for structured incident audit trails alongside Hindsight semantic memory.
- [ ] **Multi-Vector Incident Graph:** Interactive visual memory topology showing relationships between past outages in the UI.

---

## License

This project is licensed under the [MIT License](LICENSE).
