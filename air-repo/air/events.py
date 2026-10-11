"""Module 3 - Pollution event engine: evidence signal + event lifecycle (deterministic rules)."""
import math
from .validation import iso

LEVEL_RANK = {"NORMAL": 0, "ELEVATED": 1, "WARNING": 2, "SEVERE": 3}
STATE_RANK = {"NORMAL": 0, "RECOVERY": 1, "ELEVATED": 1, "WARNING": 2, "SEVERE": 3}


def detect_signal(usable, cfg, stations):
    """Corroborated evidence level from the usable readings of one cycle.

    A level needs several stations at or above its threshold, so a single abnormal
    reading (for example a faulty sensor) can never raise a regional warning.
    """
    thr = cfg["thresholds"]
    n = len(usable)
    min_st = cfg["corroboration_min_stations"]
    if n:
        min_st = max(min_st, math.ceil(cfg["corroboration_fraction"] * n))

    def over(level):
        return sorted(s for s, u in usable.items() if u["aqi"] >= thr[level])

    over_e, over_w, over_s = over("elevated"), over("warning"), over("severe")
    if len(over_s) >= min_st:
        cand = "SEVERE"
    elif len(over_w) >= min_st:
        cand = "WARNING"
    elif len(over_e) >= min_st:
        cand = "ELEVATED"
    else:
        cand = "NORMAL"

    strong = len(over_s) >= max(cfg["strong_severe_min_stations"], min_st)
    spikes = over_e if 0 < len(over_e) < min_st else []

    by_zone = {}
    for sid, u in usable.items():
        by_zone.setdefault(stations[sid]["zone"], []).append(u["aqi"])
    conflicts = sorted(z for z, v in by_zone.items()
                       if len(v) >= 2 and max(v) - min(v) > cfg["conflict_spread"])

    return {
        "candidate": cand,
        "min_stations": min_st,
        "usable_count": n,
        "over": {"elevated": over_e, "warning": over_w, "severe": over_s},
        "over_counts": {"elevated": len(over_e), "warning": len(over_w), "severe": len(over_s)},
        "strong_severe": strong,
        "uncorroborated_spikes": spikes,
        "conflict_zones": conflicts,
    }


def open_event(st, as_of):
    st["event_seq"] += 1
    event_id = "EVT-%04d" % st["event_seq"]
    st["event_id"] = event_id
    return {
        "event_id": event_id, "status": "ACTIVE", "opened_at": iso(as_of), "closed_at": None,
        "current_state": "NORMAL", "peak_state": "NORMAL", "affected_zones": [], "zones_seen": [],
        "last_area": None, "evidence_refs": [], "history": [], "updated_at": iso(as_of),
    }


def update_event(ev, decision, area, as_of):
    new = decision["new_state"]
    ev["current_state"] = new
    if new in LEVEL_RANK and LEVEL_RANK[new] > LEVEL_RANK[ev["peak_state"]]:
        ev["peak_state"] = new
    ev["affected_zones"] = list(area["zones"])
    ev["zones_seen"] = sorted(set(ev["zones_seen"]) | set(area["zones"]))
    if area["zones"]:
        ev["last_area"] = area
    ev["evidence_refs"] = sorted(set(ev["evidence_refs"]) | set(decision["evidence_refs"]))
    if decision["changed"]:
        ev["history"].append({"at": iso(as_of), "decision_id": decision["decision_id"],
                              "from": decision["previous_state"], "to": new, "reason": decision["reason"]})
    ev["updated_at"] = iso(as_of)


def close_event(ev, as_of):
    ev["status"] = "CLOSED"
    ev["closed_at"] = iso(as_of)
