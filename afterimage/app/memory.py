"""Adapter over the real Hindsight client. There is no local fallback: failures raise MemoryOffline."""
from dataclasses import dataclass, field
from hindsight_client import Hindsight


class MemoryOffline(Exception):
    pass


@dataclass
class Mem:
    id: str
    text: str
    meta: dict = field(default_factory=dict)


class HindsightMemory:
    def __init__(self, url: str, api_key: str | None, bank: str):
        self.c = Hindsight(base_url=url, api_key=api_key or None, timeout=60, max_attempts=2)
        self.bank, self._ready = bank, False

    def _call(self, fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:  # network, auth, server: all mean the memory engine is unusable
            raise MemoryOffline(f"{type(e).__name__}: {str(e)[:160]}") from e

    def ping(self) -> None:
        self._call(self.c.get_version)

    def ensure(self) -> None:
        if not self._ready:
            self._call(self.c.create_bank, bank_id=self.bank, name="Afterimage",
                       mission="Organizational incident memory: root causes, ruled-out hypotheses, fixes and recurring patterns for production services.")
            self._ready = True

    def retain(self, content: str, meta: dict, doc_id: str) -> None:
        self.ensure()
        self._call(self.c.retain, bank_id=self.bank, content=content, context="incident experience",
                   metadata=meta, tags=["afterimage"], document_id=doc_id)

    def recall(self, query: str) -> list[Mem]:
        self.ensure()
        r = self._call(self.c.recall, bank_id=self.bank, query=query, max_tokens=2048, budget="mid")
        return [Mem(str(x.id), x.text, dict(x.metadata or {})) for x in r.results]

    def items(self) -> list[dict]:
        self.ensure()
        r = self._call(self.c.list_memories, bank_id=self.bank)
        rows = getattr(r, "items", None) or getattr(r, "results", None) or []
        return [{"id": str(getattr(i, "id", "")), "text": getattr(i, "text", ""),
                 "type": getattr(i, "fact_type", None) or getattr(i, "type", None) or "memory"} for i in rows]

    def reset(self) -> None:
        self._call(self.c.delete_bank, bank_id=self.bank)
        self._ready = False
