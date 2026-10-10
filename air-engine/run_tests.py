"""Runs every demo scenario and the workflow tests. Exit code 1 if anything fails."""
import glob
import json
import os
import sys

from air import messages
from air.service import AirService

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(cond, label):
    if not cond:
        FAILS.append(label)
        print("    FAIL:", label)
    return cond


def load(name):
    with open(os.path.join(HERE, "scenarios", name + ".json")) as fh:
        return json.load(fh)


def run(name):
    data, svc = load(name), AirService()
    results = [svc.ingest_cycle(c) for c in data["cycles"]]
    return data, svc, results


def scenario_tests():
    print("SCENARIOS (all data SIMULATED)")
    for path in sorted(glob.glob(os.path.join(HERE, "scenarios", "*.json"))):
        name = os.path.basename(path)[:-5]
        data, svc, res = run(name)
        exp = data["expected"]
        states = [r["new_state"] for r in res]
        types = [a["alert_type"] for a in svc.alerts()]
        before = len(FAILS)
        check(states == exp["states"], "%s states %s != %s" % (name, states, exp["states"]))
        check(types == exp["alert_types"], "%s alert types %s != %s" % (name, types, exp["alert_types"]))
        for cyc, wanted in exp["codes"].items():
            got = res[int(cyc) - 1]["reason_codes"]
            for code in wanted:
                check(code in got, "%s cycle %s missing code %s (got %s)" % (name, cyc, code, got))
        if name == "E_missing_conflicting":
            check("IMPLAUSIBLE_AQI" in [r for q in svc.store.values("quality") for r in q["reasons"]],
                  "E: invalid reading was not flagged")
            check(res[-1]["new_state"] != "NORMAL", "E: missing data was treated as clean air")
        if name == "F_recovery":
            check(svc.events()[0]["status"] == "CLOSED", "F: event should close after sustained normal")
        if name == "F2_reescalation":
            check(len(svc.events()) == 1, "F2: re-escalation must stay in the same event")
        print("  %-24s %-4s states=%s alerts=%s" % (name, "PASS" if len(FAILS) == before else "FAIL",
                                                    ">".join(s[:4] for s in states), types))


def workflow_tests():
    print("\nWORKFLOW (authorization, AI failure, delivery, idempotency, audit) on C2_escalation")
    data, svc, _ = run("C2_escalation")
    a1, a2 = [a["alert_id"] for a in svc.alerts()]
    check(svc.status()["state"] == "SEVERE", "starting state should be SEVERE")

    # G - authorization never changes the environment
    svc.authorize(a1, "HOLD", "operator-1", "waiting for confirmation")
    check(svc.alerts()[0]["authorization_status"] == "HELD", "alert 1 should be HELD")
    for fn, label in ((lambda: svc.generate_message(a1), "message before approval"),
                      (lambda: svc.deliver(a1), "delivery before approval")):
        try:
            fn()
            check(False, label + " should be blocked")
        except PermissionError:
            pass
    svc.authorize(a2, "REJECT", "operator-1", "duplicate of newer alert")
    check(svc.status()["state"] == "SEVERE", "rejecting an alert must not change the risk state")
    check(svc.events()[0]["status"] == "ACTIVE", "rejecting an alert must not close the event")
    try:
        svc.authorize(a2, "APPROVE", "operator-1")
        check(False, "REJECTED -> APPROVED should be refused")
    except ValueError:
        pass
    svc.authorize(a1, "APPROVE", "operator-1", "confirmed")

    # H - AI failure never breaks the flow
    def boom(facts):
        raise TimeoutError("simulated Bedrock timeout")
    m = svc.generate_message(a1, ai_fn=boom)
    check(m["method"] == "TEMPLATE" and m["fallback_reason"].startswith("AI_ERROR"), "AI error -> template fallback")
    m = svc.generate_message(a1, ai_fn=lambda f: "AQI 999 everywhere. It is all clear, evacuate now.")
    check(m["method"] == "TEMPLATE" and "FAILED_VALIDATION" in m["fallback_reason"], "invented facts -> template fallback")
    m = svc.generate_message(a1, ai_fn=lambda f: messages.template_message(f).replace("WHAT TO DO", "RECOMMENDED ACTIONS"))
    check(m["method"] == "AI" and not m["problems"], "valid AI draft should be accepted")
    check(svc.status()["state"] == "SEVERE", "AI activity must not change the risk state")

    # delivery failure and retry
    d = svc.deliver(a1, "MOCK_CBS", simulate_failure=True)
    check(d["status"] == "FAILED_SIMULATED" and d["attempts"] == 1, "first delivery fails (simulated)")
    d = svc.deliver(a1, "MOCK_CBS")
    check(d["status"] == "SUBMITTED_SIMULATED" and d["attempts"] == 2, "retry succeeds on the same record")
    d = svc.deliver(a1, "MOCK_CBS")
    check(d["attempts"] == 2, "extra retry after success is ignored")
    check(len(svc.alerts()) == 2 and svc.status()["state"] == "SEVERE", "delivery retries must not create alerts or change state")

    # idempotent ingestion
    decisions_before = len(svc.history())
    dup = svc.ingest_cycle(data["cycles"][-1])
    check(dup["duplicate"] and len(svc.history()) == decisions_before and len(svc.alerts()) == 2,
          "re-sending a cycle must not create decisions or alerts")

    # I - audit trail
    t = svc.trace(a1)
    check(t["complete"], "trace should be complete")
    check(t["policy_version"] == "prototype-v1" and t["decision"]["policy_version"] == "prototype-v1", "policy version recorded")
    print("  trace(%s): %d observations, %d quality records, %d authorizations, %d messages, %d deliveries, policy %s"
          % (a1, len(t["observations"]), len(t["data_quality"]), len(t["authorizations"]),
             len(t["messages"]), len(t["deliveries"]), t["policy_version"]))
    print("  sample message (method=%s):\n%s" % (svc.store.get("messages", svc.alerts()[0]["message_id"])["method"],
          "\n".join("    | " + line for line in svc.store.get("messages", svc.alerts()[0]["message_id"])["text"].splitlines())))


if __name__ == "__main__":
    scenario_tests()
    workflow_tests()
    print("\nRESULT:", "ALL PASSED" if not FAILS else "%d FAILURE(S)" % len(FAILS))
    sys.exit(1 if FAILS else 0)
