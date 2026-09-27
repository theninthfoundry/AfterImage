"""Incident agent: observe > recall > reason > investigate > decide > verify > reflect > remember.
Memory changes the investigation order. Nothing is reported as saved unless Hindsight accepted the write."""
import time
from . import sim, llm
from .memory import MemoryOffline

LABEL = {"confirmed": "confirmed", "false": "ruled out", "partial": "partly true"}
WEIGHT = {"confirmed": 60, "false": -40, "partial": -10}


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def recall_context(mem, inc):
    q = f"{inc['service']} incident with {', '.join(inc['signals'])}: which hypotheses were ruled out, what was the root cause and the fix?"
    out = []
    for m in mem.recall(q):
        hyp, res, how = m.meta.get("hypothesis"), m.meta.get("result"), "metadata"
        if not hyp:  # fallback if Hindsight returned the fact without our metadata
            t, how = m.text.lower(), "text"
            hyp = next((h for h in sim.PRIOR if h in t), None)
            res = "false" if hyp and any(w in t for w in ("ruled out", "not the cause", "disproven")) else "confirmed" if hyp and any(w in t for w in ("root cause", "confirmed")) else None
        sig = [s for s in m.meta.get("signals", "").split(",") if s]
        rel = jaccard(inc["signals"], sig) if sig else None
        if rel is not None and rel < 0.3:
            continue
        out.append(dict(id=m.id[:8], kind=m.meta.get("kind", "fact"), hyp=hyp, result=res, relevance=rel,
                        matched=sorted(set(inc["signals"]) & set(sig)), text=m.text, parsed=how))
    return out


def rank(recalled):
    sc, adj = dict(sim.PRIOR), {}
    for r in recalled:
        if r["hyp"] in sc and r["result"] in WEIGHT:
            sc[r["hyp"]] += WEIGHT[r["result"]] * (r["relevance"] if r["relevance"] is not None else 0.5)
            adj.setdefault(r["hyp"], []).append(r["id"])
    return sorted(sc, key=lambda h: -sc[h]), sc, adj


def candidates(inc, tested, prior, lesson_text):
    base = {"incident": inc["id"], "service": inc["service"], "signals": ",".join(inc["signals"])}
    c = [dict(imp=.95, doc="incident", text=f"{inc['id']} on {inc['service']}: {inc['cause']}. Root cause: {inc['root']}. Resolved by {inc['fix'].lower()} in {inc['recovery_s']}s.",
              meta={**base, "kind": "incident", "hypothesis": inc["root"], "result": "confirmed"})]
    for t in tested:
        if t["res"] != "confirmed":
            c.append(dict(imp=.8, doc=f"hyp-{t['h']}", text=f"In {inc['id']} on {inc['service']}, hypothesis '{t['h']}' was {LABEL[t['res']]}: {t['why']}.",
                          meta={**base, "kind": "investigation", "hypothesis": t["h"], "result": t["res"]}))
    c.append(dict(imp=.85, doc="resolution", text=f"{inc['fix']} restored {inc['service']} in {inc['recovery_s']}s (simulated).", meta={**base, "kind": "resolution"}))
    if prior >= 1:
        c.append(dict(imp=.9, doc="pattern", text=lesson_text,
                      meta={**base, "kind": "pattern", "hypothesis": inc["root"], "result": "confirmed", "signals": ",".join(sim.PATTERN_SIGNALS)}))
    c += [dict(imp=.1, doc="noise-1", text="routine CPU and traffic samples", meta={}), dict(imp=.1, doc="noise-2", text="duplicate 5xx log lines", meta={})]
    return c


def make_lesson(inc, tested, prior, use_llm):
    draft = f"Pattern from {prior + 1} incidents: recent deploy + DB saturation + latency points to {inc['root']}; ruled out each time: {', '.join(t['h'] for t in tested if t['res'] == 'false') or 'none'}."
    if not use_llm:
        return draft, "templated lesson (LLM off)"
    try:
        return llm.lesson(inc, tested, draft), "lesson written by LLM"
    except llm.LLMError as e:
        return draft, f"LLM failed ({e}); templated lesson used"


class Steps(list):
    def __init__(self):
        super().__init__()
        self.t = time.perf_counter()

    def add(self, stage, headline, detail="", ok=True):
        now = time.perf_counter()
        self.append(dict(stage=stage, headline=headline, detail=detail, ok=ok, ms=round((now - self.t) * 1000)))
        self.t = now


def run_incident(inc, mem=None, use_llm=True):
    S, recalled, status = Steps(), [], "disabled" if mem is None else "online"
    S.add("observe", f"{inc['service']} is failing.", f"{len(inc['signals'])} signals: {', '.join(inc['signals'])}")
    if mem is not None:
        try:
            recalled = recall_context(mem, inc)
            S.add("recall", f"{len(recalled)} memories recalled." if recalled else "No memory yet.", f"Hindsight returned {len(recalled)} relevant items")
        except MemoryOffline as e:
            status = "offline"
            S.add("recall", "Memory engine offline.", str(e), ok=False)
    order, _, adj = rank(recalled)
    base = sorted(sim.PRIOR, key=lambda h: -sim.PRIOR[h])
    if adj:
        S.add("reason", "Hypotheses re-ranked.", "moved by memory: " + ", ".join(adj))
    tested, sec = [], 6
    for h in order:
        s, res, why = sim.HYP[h]
        sec += s
        tested.append(dict(h=h, res=res, why=why, sec=s))
        S.add("investigate", f"{h}: {LABEL[res]}.", why)
        if res == "confirmed":
            break
    S.add("decide", inc["cause"][0].upper() + inc["cause"][1:] + ".", f"root cause: {inc['root']}; action: {inc['fix']}")
    S.add("verify", f"{inc['fix']} · {inc['recovery_s']}s", "simulated recovery")
    prior = sum(1 for r in recalled if r["kind"] == "incident" and r["hyp"] == inc["root"] and r["result"] == "confirmed")
    lesson_text, how = make_lesson(inc, tested, prior, use_llm)
    S.add("reflect", "Deciding what to keep.", how)
    cands = candidates(inc, tested, prior, lesson_text)
    kept = [c for c in cands if c["imp"] >= .5]
    written = 0
    if status == "online":
        try:
            for c in kept:
                mem.retain(c["text"], c["meta"], f"{inc['id']}:{c['doc']}")
                written += 1
            S.add("remember", f"Saved {written} to Hindsight.", f"{len(cands) - len(kept)} dropped as low importance")
        except MemoryOffline as e:
            status = "offline"
            S.add("remember", "Not saved: memory engine offline.", str(e), ok=False)
    else:
        S.add("remember", "Memory disabled (baseline)." if mem is None else "Not saved: memory engine offline.", "", ok=mem is None)
    return dict(inc={k: inc[k] for k in ("id", "service", "severity", "metrics", "simulated")}, root=inc["root"], steps=list(S), recalled=recalled,
                order=order, base_order=base, tested=tested, sec=sec, wrong=sum(t["res"] != "confirmed" for t in tested),
                memory=dict(status=status, written=written, dropped=len(cands) - len(kept)))
