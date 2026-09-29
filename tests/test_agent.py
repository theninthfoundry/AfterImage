from app import agent, sim
from app.memory import Mem, MemoryOffline

I = sim.INCIDENTS


class Fake:
    """Test double with HindsightMemory's interface. Used only in tests, never shipped as a fallback."""
    def __init__(self):
        self.docs = {}

    def retain(self, content, meta, doc_id):
        self.docs[doc_id] = (content, meta)

    def recall(self, query):
        return [Mem(f"m{i:07d}", t, m) for i, (t, m) in enumerate(self.docs.values())]


class Down(Fake):
    def recall(self, query):
        raise MemoryOffline("connection refused")


def test_second_incident_changes_investigation():
    m = Fake()
    r1 = agent.run_incident(I[1], m, use_llm=False)
    r2 = agent.run_incident(I[2], m, use_llm=False)
    assert r1["wrong"] == 3 and r1["order"] == r1["base_order"]
    assert r2["order"][0] == "deployment regression" and r2["wrong"] == 0
    assert r2["sec"] < r1["sec"] and r2["recalled"]


def test_baseline_never_touches_memory():
    r = agent.run_incident(I[2], None, use_llm=False)
    assert r["order"] == r["base_order"] and r["memory"]["status"] == "disabled"


def test_offline_is_reported_not_faked():
    r = agent.run_incident(I[1], Down(), use_llm=False)
    st = {s["stage"]: s for s in r["steps"]}
    assert r["memory"]["status"] == "offline" and r["memory"]["written"] == 0
    assert not st["recall"]["ok"] and not st["remember"]["ok"]


def test_low_importance_is_dropped():
    m = Fake()
    r = agent.run_incident(I[1], m, use_llm=False)
    assert r["memory"]["dropped"] == 2 and not any("noise" in k for k in m.docs)


def test_llm_failure_is_visible_and_run_continues(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    m = Fake()
    agent.run_incident(I[1], m, use_llm=True)
    r = agent.run_incident(I[2], m, use_llm=True)
    detail = next(s for s in r["steps"] if s["stage"] == "reflect")["detail"]
    assert "LLM failed" in detail and r["memory"]["written"] > 0


def test_pattern_generalises_to_other_service():
    m = Fake()
    for i in (1, 2):
        agent.run_incident(I[i], m, use_llm=False)
    assert agent.run_incident(I[3], m, use_llm=False)["order"][0] == "deployment regression"


def test_health_reports_offline_when_hindsight_unreachable(monkeypatch):
    monkeypatch.setenv("HINDSIGHT_URL", "http://127.0.0.1:9")
    from fastapi.testclient import TestClient
    from app import main
    main._mem = None
    assert TestClient(main.app).get("/api/health").json()["memory"] == "offline"
