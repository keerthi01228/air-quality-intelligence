"""Module 5b/6/8 - Alert decision, alert records and the authorization workflow.

A risk-state change is NOT automatically a public alert, and an alert candidate is NOT
automatically authorized. Approving, holding or rejecting never changes the risk state.
"""
from .validation import iso

CONF_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def alert_type(entered_from, new):
    if entered_from == "RECOVERY":
        return "RE_ESCALATION"
    if new == "SEVERE":
        return "ESCALATION" if entered_from == "WARNING" else "SEVERE_ALERT"
    return "WARNING_ISSUED"


def _no(code, reason):
    return {"decision": "NO_ALERT", "code": code, "reason": reason, "alert_type": None, "dedupe_key": None}


def decide_alert(new, decision, area, st, cfg):
    """Return ALERT_REQUIRED or NO_ALERT with a reason and a stable dedupe key."""
    if new not in ("WARNING", "SEVERE"):
        why = {"NORMAL": "Normal conditions; no public warning needed.",
               "ELEVATED": "Elevated: monitoring only, no public warning.",
               "RECOVERY": "Recovery: conditions are improving but safety is not established; no all-clear is issued."}[new]
        return _no("STATE_NOT_ALERTABLE", why)
    if not area["zones"]:
        return _no("NO_AFFECTED_AREA", "No affected area is supported by the evidence.")

    strong = "STRONG_SEVERE_EVIDENCE" in decision["reason_codes"]
    key = "%s|%s|T%d" % (decision["event_id"], new, st["transition_seq"])
    if key not in st["alert_keys"]:
        if CONF_RANK[decision["confidence"]] < CONF_RANK[cfg["alert_min_confidence"]] and not strong:
            return _no("LOW_CONFIDENCE", "Evidence confidence is too low to justify an alert yet; keep monitoring.")
        return {"decision": "ALERT_REQUIRED", "code": "STATE_ENTRY", "dedupe_key": key,
                "alert_type": alert_type(st["entered_from"], new),
                "reason": "Meaningful change: entered %s from %s." % (new, st["entered_from"])}

    new_zones = set(area["zones"]) - set(st["last_alert_zones"])
    if len(new_zones) >= cfg["area_expansion_min_new_zones"]:
        akey = "%s|%s|AREA|%s" % (decision["event_id"], new, area["signature"])
        if akey in st["alert_keys"]:
            return _no("DUPLICATE", "An alert for this affected area already exists.")
        return {"decision": "ALERT_REQUIRED", "code": "AREA_EXPANDED", "dedupe_key": akey,
                "alert_type": "AREA_EXPANDED",
                "reason": "Affected area expanded by %d zones." % len(new_zones)}
    return _no("PERSISTENT_NO_CHANGE", "Same state and action as the existing alert; no repeat alert.")


def build_alert(st, event_id, decision, area, facts, as_of, atype, key):
    st["alert_seq"] += 1
    alert_id = "ALR-%04d" % st["alert_seq"]
    facts["alert_id"] = alert_id
    return {
        "alert_id": alert_id, "event_id": event_id, "decision_id": decision["decision_id"],
        "alert_type": atype, "state": decision["new_state"], "zones": list(area["zones"]),
        "created_at": iso(as_of), "dedupe_key": key, "authorization_status": "PENDING",
        "message_id": None, "delivery_status": None, "facts": facts,
        "policy_version": decision["policy_version"],
    }


ACTIONS = {"APPROVE": "APPROVED", "HOLD": "HELD", "REJECT": "REJECTED"}
TRANSITIONS = {"PENDING": {"APPROVED", "HELD", "REJECTED"}, "HELD": {"APPROVED", "REJECTED"},
               "APPROVED": set(), "REJECTED": set()}


def authorize(alert, action, operator, note, at, seq, policy_version):
    if action not in ACTIONS:
        raise ValueError("Unknown action %r (use APPROVE, HOLD or REJECT)" % action)
    if not operator:
        raise ValueError("An operator identity is required")
    target = ACTIONS[action]
    current = alert["authorization_status"]
    if target not in TRANSITIONS[current]:
        raise ValueError("Cannot move an alert from %s to %s" % (current, target))
    return {"authorization_id": "AUTH-%04d" % seq, "alert_id": alert["alert_id"], "from": current,
            "to": target, "operator": operator, "note": note, "at": iso(at), "policy_version": policy_version}
