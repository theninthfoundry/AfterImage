import os, uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from . import agent, sim
from .memory import HindsightMemory, MemoryOffline

load_dotenv()
app = FastAPI(title="Afterimage")
_mem: HindsightMemory | None = None


def cfg():
    return os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io"), os.getenv("HINDSIGHT_API_KEY"), os.getenv("HINDSIGHT_BANK", "afterimage")


def memory() -> HindsightMemory:
    global _mem
    if _mem is None:
        _mem = HindsightMemory(*cfg())
    return _mem


def offline(e: Exception):
    return HTTPException(503, f"MEMORY ENGINE OFFLINE: {e}")


@app.get("/api/health")
def health():
    try:
        memory().ping()
        return {"memory": "online", "llm": bool(os.getenv("GROQ_API_KEY")), "bank": cfg()[2]}
    except MemoryOffline as e:
        return {"memory": "offline", "detail": str(e), "llm": bool(os.getenv("GROQ_API_KEY"))}


@app.post("/api/incidents/{n}/run")
def run(n: int):
    if n not in sim.INCIDENTS:
        raise HTTPException(404, "unknown incident")
    return agent.run_incident(sim.INCIDENTS[n], memory())  # offline is reported inside the run, not hidden


@app.get("/api/memory")
def memories():
    try:
        return {"items": memory().items()}
    except MemoryOffline as e:
        raise offline(e)


@app.post("/api/reset")
def reset():
    try:
        memory().reset()
        return {"ok": True}
    except MemoryOffline as e:
        raise offline(e)


@app.post("/api/benchmark")
def benchmark():
    """Same three incidents twice: baseline without memory, then a fresh temporary Hindsight bank."""
    url, key, bank = cfg()
    tmp = HindsightMemory(url, key, f"{bank}-bench-{uuid.uuid4().hex[:8]}")
    try:
        tmp.ping()
    except MemoryOffline as e:
        raise offline(e)
    pick = lambda r: dict(id=r["inc"]["id"], sec=r["sec"], tested=len(r["tested"]), wrong=r["wrong"], recalled=len(r["recalled"]), memory=r["memory"]["status"])
    try:
        without = [pick(agent.run_incident(sim.INCIDENTS[i], None, use_llm=False)) for i in (1, 2, 3)]
        with_m = [pick(agent.run_incident(sim.INCIDENTS[i], tmp, use_llm=False)) for i in (1, 2, 3)]
    finally:
        try:
            tmp.reset()
        except MemoryOffline:
            pass
    return {"without": without, "with": with_m, "simulated": True}


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
