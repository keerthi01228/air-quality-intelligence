"""Module 5a - Risk-state engine (NORMAL, ELEVATED, WARNING, SEVERE, RECOVERY).

Deterministic and rule-based. The state only moves on corroborated, persistent evidence,
except strong severe evidence which may go straight to SEVERE. Missing data holds the state.
"""
import copy
from .events import LEVEL_RANK, STATE_RANK

CODE_TEXT = {
    "STRONG_SEVERE_EVIDENCE": "Strong evidence: enough stations are at severe levels at once to move directly to SEVERE.",
    "WARNING_PENDING_PERSISTENCE": "Warning-level evidence must persist for more than one cycle before the state changes.",
    "SEVERE_PENDING_PERSISTENCE": "Severe-level evidence must persist for more than one cycle before the state changes.",
    "DOWNGRADE_PENDING": "Conditions are below the current state, but improvement must persist before the state is lowered.",
    "RECOVERY_NOT_ALL_CLEAR": "RECOVERY means conditions are improving. It is not an all-clear.",
    "RE_ESCALATION": "Pollution worsened again during recovery.",
    "UNCORROBORATED_SPIKE_IGNORED": "A high reading from too few stations was not treated as a pollution event.",
    "CONFLICTING_READINGS": "Stations in the same zone disagree strongly, so confidence is reduced.",
    "CARRIED_FORWARD_READINGS": "Some readings are carried forward from earlier cycles.",
}


def new_counters():
    return {"up": {"ELEVATED": 0, "WARNING": 0, "SEVERE": 0}, "down": 0, "normal": 0}


def confidence_level(coverage, signal, carried_share):
    cand = signal["candidate"]
    if cand == "NORMAL":
        base = "HIGH" if coverage >= 0.8 else ("MEDIUM" if coverage >= 0.5 else "LOW")
        if signal["conflict_zones"] and base == "HIGH":
            base = "MEDIUM"
        return base
    k = signal["over_counts"][cand.lower()]
    score = (2 if coverage >= 0.8 else 1 if coverage >= 0.5 else 0) + (2 if k >= 3 else 1 if k >= 2 else 0)
    if signal["conflict_zones"]:
        score -= 1
    if carried_share > 0.5:
        score -= 1
    return "HIGH" if score >= 4 else ("MEDIUM" if score >= 2 else "LOW")


def build_reason(prev, new, signal, coverage, sufficient, codes, cfg):
    n, ms, cand = signal["usable_count"], signal["min_stations"], signal["candidate"]
    thr = cfg["thresholds"]
    if not sufficient:
        return ("Only %d usable stations (coverage %d%%, minimum %d%%); state held at %s. "
                "Missing data is never treated as clean air."
                % (n, round(coverage * 100), round(cfg["min_coverage"] * 100), prev))
    if cand == "NORMAL":
        text = "No level is corroborated: fewer than %d of %d usable stations are at or above %d." % (ms, n, thr["elevated"])
    else:
        k = signal["over_counts"][cand.lower()]
        text = "Evidence level %s: %d of %d usable stations are at or above %d (%d needed)." % (cand, k, n, thr[cand.lower()], ms)
    text += (" State %s -> %s." % (prev, new)) if new != prev else (" State remains %s." % new)
    for code in codes:
        if code in CODE_TEXT:
            text += " " + CODE_TEXT[code]
    return text


def assess(prev, counters, signal, coverage, carried_share, cfg):
    c = copy.deepcopy(counters)
    codes = []
    cand = signal["candidate"]
    sufficient = coverage >= cfg["min_coverage"]
    if signal["uncorroborated_spikes"]:
        codes.append("UNCORROBORATED_SPIKE_IGNORED")
    if signal["conflict_zones"]:
        codes.append("CONFLICTING_READINGS")
    if carried_share > 0:
        codes.append("CARRIED_FORWARD_READINGS")

    if not sufficient:
        codes.append("INSUFFICIENT_DATA_HOLD")
        return {"new_state": prev, "counters": c, "codes": codes, "confidence": "LOW", "sufficient": False,
                "reason": build_reason(prev, prev, signal, coverage, False, codes, cfg)}

    for level in ("ELEVATED", "WARNING", "SEVERE"):
        c["up"][level] = c["up"][level] + 1 if LEVEL_RANK[cand] >= LEVEL_RANK[level] else 0
    achieved = "NORMAL"
    for level in ("ELEVATED", "WARNING", "SEVERE"):
        if c["up"][level] >= cfg["persistence"][level.lower()]:
            achieved = level
    if signal["strong_severe"]:
        achieved = "SEVERE"
        codes.append("STRONG_SEVERE_EVIDENCE")

    if prev == "NORMAL":
        new = achieved
    elif prev in ("ELEVATED", "WARNING", "SEVERE"):
        if LEVEL_RANK[achieved] > LEVEL_RANK[prev]:
            new, c["down"] = achieved, 0
        elif LEVEL_RANK[cand] >= LEVEL_RANK[prev]:
            new, c["down"] = prev, 0
        else:
            c["down"] += 1
            if c["down"] >= cfg["down_cycles"]:
                new = "NORMAL" if prev == "ELEVATED" else "RECOVERY"
                c["down"], c["normal"] = 0, 0
            else:
                new = prev
                codes.append("DOWNGRADE_PENDING")
    else:  # RECOVERY
        if LEVEL_RANK[achieved] >= LEVEL_RANK["WARNING"]:
            new = achieved
            c["normal"] = 0
            codes.append("RE_ESCALATION")
        else:
            c["normal"] = c["normal"] + 1 if cand == "NORMAL" else 0
            if c["normal"] >= cfg["normal_cycles"]:
                new = "NORMAL"
            else:
                new = "RECOVERY"
                codes.append("RECOVERY_NOT_ALL_CLEAR")

    if new == "RECOVERY" and "RECOVERY_NOT_ALL_CLEAR" not in codes:
        codes.append("RECOVERY_NOT_ALL_CLEAR")
    if STATE_RANK[cand] > STATE_RANK[new] and cand in ("WARNING", "SEVERE"):
        codes.append(cand + "_PENDING_PERSISTENCE")
    if new == "NORMAL" and prev != "NORMAL":
        c = new_counters()

    return {"new_state": new, "counters": c, "codes": codes,
            "confidence": confidence_level(coverage, signal, carried_share), "sufficient": True,
            "reason": build_reason(prev, new, signal, coverage, True, codes, cfg)}
