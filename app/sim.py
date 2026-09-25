"""Deterministic simulated production environment. Everything here is labelled simulated in the UI."""
HYP = {  # hypothesis -> (simulated test seconds, true outcome, evidence)
    "external provider": (14, "false", "provider latency stayed normal"),
    "database overload": (18, "partial", "connections high but query latency normal: a symptom, not the cause"),
    "network issue": (9, "false", "network metrics normal"),
    "deployment regression": (12, "confirmed", "deploy preceded the spike and changed pool settings"),
}
PRIOR = {"external provider": 50, "database overload": 45, "network issue": 40, "deployment regression": 30}
PATTERN_SIGNALS = ["latency-spike", "db-saturation", "recent-deploy", "5xx-rise"]


def _inc(n, svc, sev, sig, metrics, ver, cause, rec):
    return dict(n=n, id=f"INC-{n:03d}", service=svc, severity=sev, signals=sig, metrics=metrics,
                root="deployment regression", cause=cause, fix=f"Rollback {ver}", recovery_s=rec, simulated=True)


INCIDENTS = {
    1: _inc(1, "payment-api", "P1", ["payment-api", "latency-spike", "db-saturation", "5xx-rise", "recent-deploy"],
            [["error rate", "18.4%"], ["latency", "420ms → 2.8s"], ["db connections", "82% → 99%"], ["deploy", "v3.4.2, 11m ago"]],
            "v3.4.2", "connection pool exhaustion introduced in v3.4.2", 462),
    2: _inc(2, "payment-api", "P1", ["payment-api", "checkout-latency", "db-saturation", "5xx-rise", "recent-deploy"],
            [["error rate", "0.2% → 6.7%"], ["latency", "180ms → 1.9s"], ["db connections", "79%"], ["deploy", "v3.5.0, 9m ago"]],
            "v3.5.0", "connection pool exhaustion introduced in v3.5.0", 198),
    3: _inc(3, "orders-api", "P2", ["orders-api", "latency-spike", "db-saturation", "recent-deploy"],
            [["error rate", "0.4% → 3.1%"], ["latency", "240ms → 1.4s"], ["db connections", "74% → 96%"], ["deploy", "v1.9.3, 14m ago"]],
            "v1.9.3", "connection pool exhaustion introduced in v1.9.3", 175),
}
