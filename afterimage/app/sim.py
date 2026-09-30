"""Deterministic simulated production environment. Everything here is labelled simulated in the UI.

Each incident has its OWN hypothesis set and prior scores — deliberately not shared across
incidents. INC-001/002/003 share a root-cause family (deployment regression) so the demo can show
memory transferring a lesson across two payment-api incidents and generalising to a different
service. INC-004/005 are unrelated failure families with no repeat partner, so a run against them
proves memory does NOT wrongly transfer facts across incidents whose signals don't overlap.
"""

WEIGHT = {"confirmed": 60, "false": -40, "partial": -10}


def _h(sec, result, why):
    return {"sec": sec, "result": result, "why": why}


def _inc(n, svc, sev, sig, metrics, root, cause, fix, rec, hyp, prior):
    return dict(n=n, id=f"INC-{n:03d}", service=svc, severity=sev, signals=sig, metrics=metrics,
                root=root, cause=cause, fix=fix, recovery_s=rec, simulated=True, hyp=hyp, prior=prior)


INCIDENTS = {
    1: _inc(1, "payment-api", "P1",
            ["payment-api", "latency-spike", "db-saturation", "5xx-rise", "recent-deploy"],
            [["error rate", "18.4%"], ["latency", "420ms → 2.8s"], ["db connections", "82% → 99%"], ["deploy", "v3.4.2, 11m ago"]],
            "deployment regression", "connection pool exhaustion introduced in v3.4.2", "Rollback v3.4.2", 462,
            {"external provider": _h(14, "false", "provider latency stayed normal"),
             "database overload": _h(18, "partial", "connections high but query latency normal: a symptom, not the cause"),
             "network issue": _h(9, "false", "network metrics normal"),
             "deployment regression": _h(12, "confirmed", "deploy preceded the spike and changed pool settings")},
            {"external provider": 50, "database overload": 45, "network issue": 40, "deployment regression": 30}),
    2: _inc(2, "payment-api", "P1",
            ["payment-api", "checkout-latency", "db-saturation", "5xx-rise", "recent-deploy"],
            [["error rate", "0.2% → 6.7%"], ["latency", "180ms → 1.9s"], ["db connections", "79%"], ["deploy", "v3.5.0, 9m ago"]],
            "deployment regression", "connection pool exhaustion introduced in v3.5.0", "Rollback v3.5.0", 198,
            {"external provider": _h(14, "false", "provider latency stayed normal"),
             "database overload": _h(18, "partial", "connections high but query latency normal: a symptom, not the cause"),
             "network issue": _h(9, "false", "network metrics normal"),
             "deployment regression": _h(12, "confirmed", "deploy preceded the spike and changed pool settings")},
            {"external provider": 50, "database overload": 45, "network issue": 40, "deployment regression": 30}),
    3: _inc(3, "orders-api", "P2",
            ["orders-api", "latency-spike", "db-saturation", "recent-deploy"],
            [["error rate", "0.4% → 3.1%"], ["latency", "240ms → 1.4s"], ["db connections", "74% → 96%"], ["deploy", "v1.9.3, 14m ago"]],
            "deployment regression", "connection pool exhaustion introduced in v1.9.3", "Rollback v1.9.3", 175,
            {"external provider": _h(14, "false", "provider latency stayed normal"),
             "database overload": _h(18, "partial", "connections high but query latency normal: a symptom, not the cause"),
             "network issue": _h(9, "false", "network metrics normal"),
             "deployment regression": _h(12, "confirmed", "deploy preceded the spike and changed pool settings")},
            {"external provider": 50, "database overload": 45, "network issue": 40, "deployment regression": 30}),
    4: _inc(4, "auth-service", "P1",
            ["auth-service", "cache-miss-spike", "login-failure-rise", "redis-latency"],
            [["login failure rate", "0.3% → 22%"], ["cache hit rate", "97% → 41%"], ["redis latency", "2ms → 340ms"], ["redis memory", "94% (evicting)"]],
            "redis eviction thrashing", "Redis maxmemory reached; hot session keys evicted under LRU pressure", "Raise Redis maxmemory + isolate session DB", 301,
            {"upstream idp outage": _h(11, "false", "identity provider status page green, direct pings under 20ms"),
             "auth token bug": _h(16, "false", "token verification logic unchanged since last deploy"),
             "network partition": _h(8, "partial", "one AZ showed elevated latency but not full partition"),
             "redis eviction thrashing": _h(15, "confirmed", "eviction counter climbing in lockstep with failure rate")},
            {"upstream idp outage": 55, "auth token bug": 35, "network partition": 30, "redis eviction thrashing": 25}),
    5: _inc(5, "api-gateway", "P2",
            ["api-gateway", "rate-limit-errors", "upstream-timeout-rise", "traffic-surge"],
            [["429 rate", "0.1% → 14.6%"], ["upstream p99", "220ms → 1.1s"], ["req/s", "1,200 → 9,800"], ["config", "rate-limit tier unchanged"]],
            "rate limiter misconfiguration", "Per-tenant rate-limit bucket sized for old traffic tier after a silent plan upgrade", "Resize rate-limit buckets to current tier", 240,
            {"ddos attack": _h(13, "false", "traffic came from a single known enterprise tenant, not distributed sources"),
             "upstream service degraded": _h(17, "partial", "upstream p99 rose, but only after the gateway began throttling"),
             "config drift": _h(10, "false", "gateway config matches the last approved deploy"),
             "rate limiter misconfiguration": _h(9, "confirmed", "tenant's traffic tier was upgraded but bucket size was never updated")},
            {"ddos attack": 50, "upstream service degraded": 40, "config drift": 35, "rate limiter misconfiguration": 30}),
}

FAMILIES = {"deployment regression": [1, 2, 3]}  # incidents that intentionally share a root cause, for the demo
