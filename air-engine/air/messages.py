"""Module 7 - Alert message engine. AI may only reword APPROVED FACTS and never decides anything."""
import copy
import json
import re

FORBIDDEN_TERMS = ["all clear", "all-clear", "safe to go outside", "no risk", "no longer a risk",
                   "evacuate", "evacuation", "lockdown", "curfew"]


def build_facts(state, atype, decision, area, cfg, zones, source_label):
    usable = decision["snapshot"]["usable"]
    over_counts = decision["signal"]["over_counts"]
    guidance = cfg["guidance"][state]
    return {
        "alert_id": None, "state": state, "alert_type": atype,
        "zones": [zones[z]["name"] for z in area["zones"]], "zone_ids": list(area["zones"]),
        "max_aqi": int(round(max(u["aqi"] for u in usable.values()))) if usable else 0,
        "stations_reporting": len(usable),
        "stations_over_threshold": over_counts[state.lower()],
        "threshold": cfg["thresholds"][state.lower()],
        "as_of": decision["as_of"], "confidence": decision["confidence"],
        "headline": guidance["headline"], "actions": list(guidance["actions"]),
        "avoid": list(guidance["avoid"]), "extra_care": list(guidance["extra_care"]),
        "source_label": source_label, "guidance_label": cfg["guidance_label"],
        "policy_version": decision["policy_version"],
    }


def template_message(f):
    lines = []
    if "SIMULATED" in f["source_label"].upper():
        lines.append("[SIMULATED DEMO - NOT A REAL WARNING]")
    lines += ["AIR QUALITY ALERT - %s" % f["state"], "",
              "WHERE: " + ", ".join(f["zones"]),
              "WHAT IS HAPPENING: %s Highest reading: AQI %d. %d of %d reporting stations are at or above the "
              "prototype %s threshold (%d)." % (f["headline"], f["max_aqi"], f["stations_over_threshold"],
                                                f["stations_reporting"], f["state"], f["threshold"]),
              "HOW SERIOUS: %s (confidence: %s)" % (f["state"], f["confidence"]), "", "WHAT TO DO:"]
    lines += ["- " + a for a in f["actions"]]
    lines += ["", "WHAT TO AVOID:"] + ["- " + a for a in f["avoid"]]
    lines += ["", "WHO SHOULD TAKE EXTRA CARE:"] + ["- " + a for a in f["extra_care"]]
    lines += ["", "UPDATED: %s (UTC)" % f["as_of"], "SOURCE: %s. %s" % (f["source_label"], f["guidance_label"])]
    return "\n".join(lines)


def validate_message(text, facts):
    """Check a draft against the approved facts. Returns a list of problems (empty = OK)."""
    problems = []
    if not isinstance(text, str) or not text.strip():
        return ["EMPTY_OR_NOT_TEXT"]
    if facts["state"] not in text.upper():
        problems.append("MISSING_STATE")
    for z in facts["zones"]:
        if z not in text:
            problems.append("MISSING_ZONE:" + z)
    if facts["as_of"] not in text:
        problems.append("MISSING_UPDATE_TIME")
    allowed = set(re.findall(r"\d+", json.dumps(facts, ensure_ascii=False)))
    for tok in sorted(set(re.findall(r"\d+", text))):
        if tok not in allowed:
            problems.append("UNSUPPORTED_NUMBER:" + tok)
    low = text.lower()
    for term in FORBIDDEN_TERMS:
        if term in low:
            problems.append("FORBIDDEN_TERM:" + term)
    if "SIMULATED" in facts["source_label"].upper() and "SIMULATED" not in text.upper():
        problems.append("MISSING_SIMULATION_LABEL")
    if len(text) > 2500:
        problems.append("TOO_LONG")
    return problems


def generate_message(facts, ai_fn=None):
    """Try the AI drafter (if any); fall back to the approved template if it fails or drifts."""
    fallback_reason = None
    if ai_fn is not None:
        try:
            draft = ai_fn(copy.deepcopy(facts))     # the drafter only ever sees the approved facts
        except Exception as exc:                    # Bedrock error, timeout, throttling ...
            fallback_reason = "AI_ERROR:" + type(exc).__name__
        else:
            problems = validate_message(draft, facts)
            if not problems:
                return {"text": draft, "method": "AI", "problems": [], "fallback_reason": None}
            fallback_reason = "AI_OUTPUT_FAILED_VALIDATION:" + ",".join(problems[:5])
    text = template_message(facts)
    return {"text": text, "method": "TEMPLATE", "problems": validate_message(text, facts),
            "fallback_reason": fallback_reason}
