"""Structured application state: what actually happened, when, and how long each stage took.

This is deliberately separate from Hindsight. Hindsight holds *experience* — facts the agent can
recall and reason with. This module holds the *audit trail* — a plain relational record of every
run and every stage, independent of whether Hindsight was reachable at the time. It answers
"what happened" (section 24/33 of the brief: AgentRun, run ID, stage, timestamp, duration,
success/failure) without needing Hindsight at all, and the memory graph (/api/graph) is built
entirely from this table so it still works when the memory engine is offline.

Defaults to a local SQLite file so the project runs with zero setup; point DATABASE_URL at
Postgres for anything beyond a demo.
"""
import datetime
from datetime import timezone
import os
import uuid

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                         String, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Run(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True)
    incident_ref = Column(String, index=True)     # e.g. "INC-001"
    service = Column(String, index=True)
    severity = Column(String)
    root_cause = Column(String, index=True)
    fix = Column(String)
    recovery_s = Column(Integer)
    diagnosis_sec = Column(Integer)
    wrong = Column(Integer)
    memory_status = Column(String)
    memory_written = Column(Integer)
    recalled_count = Column(Integer)
    started_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc), index=True)
    stages = relationship("Stage", backref="run", cascade="all, delete-orphan", order_by="Stage.seq")


class Stage(Base):
    __tablename__ = "stages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    seq = Column(Integer)
    stage = Column(String)
    headline = Column(String)
    detail = Column(String)
    ok = Column(Boolean)
    ms = Column(Integer)


_engine = None
_Session = None


def _build(url: str):
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    return engine


def configure(url: str | None = None):
    """(Re)build the engine. Called once at import with DATABASE_URL, and by tests with an
    isolated sqlite URL so test runs never share state with each other or with a real database."""
    global _engine, _Session
    _engine = _build(url or os.getenv("DATABASE_URL", "sqlite:///./afterimage.db"))
    _Session = sessionmaker(bind=_engine)


def session():
    if _Session is None:
        configure()
    return _Session()


def record_run(db, result: dict) -> str:
    run_id = str(uuid.uuid4())
    r = Run(id=run_id, incident_ref=result["inc"]["id"], service=result["inc"]["service"],
            severity=result["inc"]["severity"], root_cause=result["root"], fix=result["fix"],
            recovery_s=result["recovery_s"], diagnosis_sec=result["sec"], wrong=result["wrong"],
            memory_status=result["memory"]["status"], memory_written=result["memory"]["written"],
            recalled_count=len(result["recalled"]))
    for i, s in enumerate(result["steps"]):
        r.stages.append(Stage(seq=i, stage=s["stage"], headline=s["headline"], detail=s["detail"], ok=s["ok"], ms=s["ms"]))
    db.add(r)
    db.commit()
    return run_id


def list_runs(db, limit=50):
    return db.query(Run).order_by(Run.started_at.desc()).limit(limit).all()


def build_graph(db):
    """Nodes/edges derived purely from the audit trail — works even with Hindsight offline."""
    runs = db.query(Run).order_by(Run.started_at.asc()).all()
    nodes, edges, seen = [], [], set()

    def node(id_, kind, label):
        if id_ not in seen:
            seen.add(id_)
            nodes.append({"id": id_, "kind": kind, "label": label})
        return id_

    by_root = {}
    for r in runs:
        inc_id = f"inc:{r.id}"
        svc_id = f"svc:{r.service}"
        root_id = f"root:{r.root_cause}"
        fix_id = f"fix:{r.fix}"
        node(inc_id, "incident", r.incident_ref)
        node(svc_id, "service", r.service)
        node(root_id, "root_cause", r.root_cause)
        node(fix_id, "resolution", r.fix)
        edges.append({"from": inc_id, "to": svc_id, "rel": "affected"})
        edges.append({"from": inc_id, "to": root_id, "rel": "caused_by"})
        edges.append({"from": root_id, "to": fix_id, "rel": "resolved_by"})
        by_root.setdefault(r.root_cause, []).append(inc_id)
    for root, incs in by_root.items():
        for a, b in zip(incs, incs[1:]):
            edges.append({"from": a, "to": b, "rel": "similar_to"})
    return {"nodes": nodes, "edges": edges}
