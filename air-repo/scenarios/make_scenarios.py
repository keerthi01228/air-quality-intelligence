"""Generates the repeatable, SIMULATED demo scenarios (JSON). Re-run to regenerate."""
import json
import os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATIONS = ["ST-N1", "ST-N2", "ST-C1", "ST-E1", "ST-S1", "ST-S2"]
START = datetime(2026, 10, 10, 6, 0, 0, tzinfo=timezone.utc)
N = None


def ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def cycle(scn, i, values):
    """values: one entry per station: a number, None (no report) or a dict of field overrides."""
    as_of = START + timedelta(minutes=15 * (i - 1))
    obs = []
    for sid, v in zip(STATIONS, values):
        if v is None:
            continue
        o = {"observation_id": "%s-c%02d-%s" % (scn, i, sid), "station_id": sid,
             "timestamp": ts(as_of - timedelta(minutes=2)), "aqi": v, "source": "SIMULATED"}
        if isinstance(v, dict):
            o["aqi"] = None
            o.update(v)
        obs.append(o)
    return {"cycle_id": "%s-c%02d" % (scn, i), "as_of": ts(as_of), "observations": obs}


def scenario(name, description, rows, states, alerts, codes=None):
    return {"name": name, "description": description, "simulated": True,
            "cycles": [cycle(name, i + 1, r) for i, r in enumerate(rows)],
            "expected": {"states": states, "alert_types": alerts, "codes": codes or {}}}


NORMAL = [88, 84, 96, 90, 72, 75]
S = {}
S["A_normal"] = scenario(
    "A_normal", "Normal conditions: valid readings that never meet a warning rule. No alert expected.",
    [[82, 78, 95, 88, 70, 74], [85, 80, 98, 92, 72, 76], [90, 84, 101, 95, 75, 79],
     [88, 82, 99, 93, 74, 77], [84, 79, 96, 90, 71, 75], [86, 81, 97, 91, 73, 76]],
    ["NORMAL"] * 6, [])

S["B_gradual"] = scenario(
    "B_gradual", "Gradual pollution: NORMAL -> ELEVATED -> WARNING with exactly one alert (no spam).",
    [NORMAL, [165, 172, 158, 110, 95, 90], [215, 228, 205, 160, 120, 110], [224, 236, 214, 172, 130, 118],
     [230, 241, 219, 181, 140, 125], [226, 238, 211, 176, 136, 122]],
    ["NORMAL", "ELEVATED", "ELEVATED", "WARNING", "WARNING", "WARNING"], ["WARNING_ISSUED"],
    {"3": ["WARNING_PENDING_PERSISTENCE"]})

S["C_sudden_severe"] = scenario(
    "C_sudden_severe", "Sudden severe pollution: strong corroborated evidence moves NORMAL -> SEVERE directly.",
    [NORMAL, [380, 410, 352, 340, 120, 110], [372, 404, 347, 338, 126, 114], [361, 395, 340, 331, 131, 118]],
    ["NORMAL", "SEVERE", "SEVERE", "SEVERE"], ["SEVERE_ALERT"], {"2": ["STRONG_SEVERE_EVIDENCE"]})

S["C2_escalation"] = scenario(
    "C2_escalation", "Escalation: WARNING deteriorates to SEVERE and a second alert is justified.",
    [NORMAL, [165, 172, 158, 110, 95, 90], [215, 228, 205, 160, 120, 110], [224, 236, 214, 172, 130, 118],
     [335, 352, 318, 240, 150, 140], [342, 360, 325, 250, 160, 150]],
    ["NORMAL", "ELEVATED", "ELEVATED", "WARNING", "SEVERE", "SEVERE"], ["WARNING_ISSUED", "ESCALATION"])

S["D_persistent"] = scenario(
    "D_persistent", "Persistent pollution: readings fluctuate around the threshold but only one alert is raised.",
    [NORMAL, [165, 172, 158, 110, 95, 90], [215, 228, 205, 160, 120, 110], [224, 236, 214, 172, 130, 118],
     [225, 232, 212, 175, 130, 120], [219, 226, 205, 170, 128, 119], [208, 198, 196, 165, 126, 118],
     [221, 229, 207, 172, 129, 121], [216, 224, 203, 168, 127, 120], [214, 221, 201, 166, 125, 119]],
    ["NORMAL", "ELEVATED", "ELEVATED"] + ["WARNING"] * 7, ["WARNING_ISSUED"], {"7": ["DOWNGRADE_PENDING"]})

S["E_missing_conflicting"] = scenario(
    "E_missing_conflicting",
    "Faulty/uncorroborated readings, an invalid reading, then stations go silent during a WARNING: the state is held.",
    [[90, 85, 100, 495, 88, {"aqi": 999}],            # faulty E1 spike + invalid S2 value
     [335, 55, 95, 480, 85, 90],                      # N1 and N2 conflict, spike persists but is not corroborated
     [210, 224, 205, 170, 120, 115], [215, 230, 208, 172, 125, 118],
     [232, 236, N, N, N, N], [234, N, N, N, N, N], [236, N, N, N, N, N],
     [233, N, N, N, N, N], [231, N, N, N, N, N], [230, N, N, N, N, N]],
    ["NORMAL", "NORMAL", "ELEVATED", "WARNING", "WARNING", "WARNING", "WARNING", "WARNING", "WARNING", "WARNING"],
    ["WARNING_ISSUED"],
    {"1": ["UNCORROBORATED_SPIKE_IGNORED"], "2": ["UNCORROBORATED_SPIKE_IGNORED", "CONFLICTING_READINGS"],
     "5": ["CARRIED_FORWARD_READINGS"], "8": ["INSUFFICIENT_DATA_HOLD"], "10": ["INSUFFICIENT_DATA_HOLD"]})

RECOVERY_ROWS = [NORMAL, [380, 410, 352, 340, 120, 110], [372, 404, 347, 338, 126, 114],
                 [270, 285, 255, 220, 160, 150], [210, 222, 198, 170, 140, 130],
                 [150, 160, 140, 130, 120, 115]]
S["F_recovery"] = scenario(
    "F_recovery", "Recovery: SEVERE -> RECOVERY -> NORMAL without a premature all-clear.",
    RECOVERY_ROWS + [[120, 125, 110, 105, 100, 98], [105, 110, 100, 95, 90, 92]],
    ["NORMAL", "SEVERE", "SEVERE", "SEVERE", "RECOVERY", "RECOVERY", "RECOVERY", "NORMAL"], ["SEVERE_ALERT"],
    {"5": ["RECOVERY_NOT_ALL_CLEAR"]})

S["F2_reescalation"] = scenario(
    "F2_reescalation", "Re-escalation: pollution worsens again during RECOVERY and a new alert is raised.",
    RECOVERY_ROWS + [[235, 241, 220, 180, 130, 125], [238, 245, 224, 185, 133, 128], [232, 240, 219, 178, 131, 126]],
    ["NORMAL", "SEVERE", "SEVERE", "SEVERE", "RECOVERY", "RECOVERY", "RECOVERY", "WARNING", "WARNING"],
    ["SEVERE_ALERT", "RE_ESCALATION"], {"8": ["RE_ESCALATION"]})

if __name__ == "__main__":
    for name, data in S.items():
        with open(os.path.join(HERE, name + ".json"), "w") as fh:
            json.dump(data, fh, indent=2)
    print("wrote", len(S), "scenarios")
