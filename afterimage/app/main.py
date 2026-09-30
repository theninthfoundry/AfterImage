import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import agent, db, sim
from .memory import HindsightMemory, MemoryOffline

load_dotenv()
db.configure()  # DATABASE_URL, defaults to a local sqlite file
app = FastAPI(title="Afterimage")
_mem: HindsightMemory | None = None


def cfg():
    return os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io"), os.getenv("HINDSIGHT_API_KEY"), os.getenv("HINDSIGHT_BANK", "afterimage")


def memory() -> HindsightMemory:
    global _mem
    if _mem is None:
        _mem = HindsightMemory(*cfg())
    return _mem


def get_db():
    s = db.session()
    try:
        yield s
    finally:
        s.close()


def offline(e: Exception):
    return HTTPException(503, f"MEMORY ENGINE OFFLINE: {e}")


@app.get("/api/health")
def health():
    try:
        memory().ping()
        return {"memory": "online", "llm": bool(os.getenv("GROQ_API_KEY")), "bank": cfg()[2]}
    except MemoryOffline as e:
        return {"memory": "offline", "detail": str(e), "llm": bool(os.getenv("GROQ_API_KEY"))}


@app.get("/api/incidents")
def list_incidents():
    return {"incidents": [{"n": i["n"], "id": i["id"], "service": i["service"], "severity": i["severity"]} for i in sim.INCIDENTS.values()]}


@app.post("/api/incidents/{n}/run")
def run(n: int, session=Depends(get_db)):
    if n not in sim.INCIDENTS:
        raise HTTPException(404, "unknown incident")
    result = agent.run_incident(sim.INCIDENTS[n], memory())  # offline is reported inside the run, not hidden
    db.record_run(session, result)  # structured audit trail, independent of Hindsight reachability
    return result


@app.get("/api/memory")
def memories():
    try:
        return {"items": memory().items()}
    except MemoryOffline as e:
        raise offline(e)


@app.get("/api/runs")
def runs(session=Depends(get_db)):
    rows = db.list_runs(session)
    return {"runs": [{"id": r.id, "incident": r.incident_ref, "service": r.service, "root_cause": r.root_cause,
                     "fix": r.fix, "diagnosis_sec": r.diagnosis_sec, "wrong": r.wrong, "memory_status": r.memory_status,
                     "memory_written": r.memory_written, "recalled": r.recalled_count,
                     "started_at": r.started_at.isoformat() + "Z",
                     "stages": [{"stage": s.stage, "ok": s.ok, "ms": s.ms} for s in r.stages]} for r in rows]}


@app.get("/api/graph")
def graph(session=Depends(get_db)):
    """Built entirely from the structured audit trail, not from Hindsight — works offline too."""
    return db.build_graph(session)


@app.post("/api/reset")
def reset():
    try:
        memory().reset()
        return {"ok": True}
    except MemoryOffline as e:
        raise offline(e)


@app.post("/api/benchmark")
def benchmark():
    """The deployment-regression family (INC-001→003) run twice: baseline without memory, then
    against a fresh temporary Hindsight bank. Not recorded in the audit trail — this is an A/B
    measurement, not an operational run."""
    url, key, bank = cfg()
    tmp = HindsightMemory(url, key, f"{bank}-bench-{uuid.uuid4().hex[:8]}")
    try:
        tmp.ping()
    except MemoryOffline as e:
        raise offline(e)
    ids = sim.FAMILIES["deployment regression"]
    pick = lambda r: dict(id=r["inc"]["id"], sec=r["sec"], tested=len(r["tested"]), wrong=r["wrong"], recalled=len(r["recalled"]), memory=r["memory"]["status"])
    try:
        without = [pick(agent.run_incident(sim.INCIDENTS[i], None, use_llm=False)) for i in ids]
        with_m = [pick(agent.run_incident(sim.INCIDENTS[i], tmp, use_llm=False)) for i in ids]
    finally:
        try:
            tmp.reset()
        except MemoryOffline:
            pass
    return {"without": without, "with": with_m, "simulated": True}


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
