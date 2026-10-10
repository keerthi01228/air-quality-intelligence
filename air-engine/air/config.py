"""AIR prototype configuration.

IMPORTANT: every threshold here is a PROTOTYPE demonstration rule. These are NOT official
government (CPCB / NDMA) thresholds. On AWS they are loaded from Systems Manager Parameter
Store so every decision can record which policy version was active.
"""
import copy

POLICY_VERSION = "prototype-v1"

GUIDANCE = {
    "WARNING": {
        "headline": "Air quality is poor in the areas listed.",
        "actions": [
            "Limit time outdoors, especially strenuous activity.",
            "Keep windows and doors closed when outdoor air is worse than indoor air.",
            "Follow advice from local health and pollution-control authorities.",
        ],
        "avoid": ["Avoid outdoor exercise and long periods outside."],
        "extra_care": [
            "Children, older adults, pregnant people, and people with heart or lung conditions should take extra care.",
        ],
    },
    "SEVERE": {
        "headline": "Air quality is severely degraded in the areas listed.",
        "actions": [
            "Stay indoors where possible and keep windows and doors closed.",
            "Postpone non-essential outdoor activity and travel.",
            "Follow instructions from local authorities.",
        ],
        "avoid": ["Avoid all strenuous outdoor activity."],
        "extra_care": [
            "Children, older adults, pregnant people, and people with heart or lung conditions should take extra care.",
            "If you feel unwell, contact a health professional.",
        ],
    },
}

DEFAULT_CONFIG = {
    "policy_version": POLICY_VERSION,
    "thresholds": {"elevated": 150, "warning": 200, "severe": 300},   # prototype AQI levels
    "aqi_min": 0,
    "aqi_max": 500,
    "stale_minutes": 60,                 # older readings are STALE (not used as fresh evidence)
    "future_tolerance_minutes": 10,
    "min_coverage": 0.5,                 # below this share of usable stations => hold state
    "corroboration_min_stations": 2,
    "corroboration_fraction": 0.4,       # needed stations = max(2, ceil(0.4 * usable))
    "strong_severe_min_stations": 3,     # strong evidence => NORMAL -> SEVERE directly
    "persistence": {"elevated": 1, "warning": 2, "severe": 2},   # cycles of evidence needed
    "down_cycles": 2,                    # cycles of improvement before leaving a state
    "normal_cycles": 3,                  # clean cycles in RECOVERY before NORMAL
    "conflict_spread": 200,              # AQI spread inside one zone that counts as conflicting
    "area_expansion_min_new_zones": 2,
    "zone_radius_km": 4.0,
    "alert_min_confidence": "MEDIUM",
    "guidance": GUIDANCE,
    "guidance_label": "Prototype guidance - to be replaced by authority-approved text.",
}

# Simulated demo stations (placeholder coordinates, NOT real monitoring stations).
STATIONS = {
    "ST-N1": {"name": "Demo Station N1 (simulated)", "zone": "NORTH",   "lat": 17.4500, "lon": 78.4700},
    "ST-N2": {"name": "Demo Station N2 (simulated)", "zone": "NORTH",   "lat": 17.4600, "lon": 78.4900},
    "ST-C1": {"name": "Demo Station C1 (simulated)", "zone": "CENTRAL", "lat": 17.3850, "lon": 78.4867},
    "ST-E1": {"name": "Demo Station E1 (simulated)", "zone": "EAST",    "lat": 17.4000, "lon": 78.5600},
    "ST-S1": {"name": "Demo Station S1 (simulated)", "zone": "SOUTH",   "lat": 17.3200, "lon": 78.4700},
    "ST-S2": {"name": "Demo Station S2 (simulated)", "zone": "SOUTH",   "lat": 17.3100, "lon": 78.4900},
}

ZONES = {
    "NORTH":   {"name": "Demo North",   "lat": 17.455, "lon": 78.480},
    "CENTRAL": {"name": "Demo Central", "lat": 17.385, "lon": 78.4867},
    "EAST":    {"name": "Demo East",    "lat": 17.400, "lon": 78.560},
    "SOUTH":   {"name": "Demo South",   "lat": 17.315, "lon": 78.480},
}


def get_config(overrides=None):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    return cfg
