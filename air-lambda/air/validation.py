"""Module 2 - Data validation & quality. Missing or unusable data is never clean air."""
from datetime import datetime, timezone


def parse_ts(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_observation(obs, as_of, cfg, stations):
    """Return a data-quality assessment: status VALID | STALE | INVALID plus reason codes."""
    reasons = []
    status = "VALID"

    def bad(code):
        nonlocal status
        status = "INVALID"
        reasons.append(code)

    for field in ("observation_id", "station_id", "timestamp", "aqi"):
        if obs.get(field) in (None, ""):
            bad("MISSING_FIELD:" + field)

    sid = obs.get("station_id")
    if sid and sid not in stations:
        bad("UNKNOWN_STATION")

    ts = None
    if obs.get("timestamp") not in (None, ""):
        try:
            ts = parse_ts(obs["timestamp"])
        except Exception:
            bad("BAD_TIMESTAMP")

    aqi = obs.get("aqi")
    if aqi not in (None, ""):
        if isinstance(aqi, bool) or not isinstance(aqi, (int, float)) or aqi != aqi:
            bad("AQI_NOT_NUMERIC")
        elif aqi < cfg["aqi_min"] or aqi > cfg["aqi_max"]:
            bad("IMPLAUSIBLE_AQI")

    lat, lon = obs.get("lat"), obs.get("lon")
    if lat is not None or lon is not None:
        try:
            ok = -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
        except (TypeError, ValueError):
            ok = False
        if not ok:
            bad("BAD_COORDINATES")

    for name, value in (obs.get("pollutants") or {}).items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            bad("BAD_POLLUTANT:" + name)

    age = None
    if ts is not None and status == "VALID":
        age = (as_of - ts).total_seconds() / 60.0
        if age < -cfg["future_tolerance_minutes"]:
            bad("FUTURE_TIMESTAMP")
        elif age > cfg["stale_minutes"]:
            status = "STALE"
            reasons.append("STALE_OBSERVATION")

    return {
        "observation_id": obs.get("observation_id"),
        "station_id": sid,
        "status": status,
        "reasons": reasons,
        "age_minutes": None if age is None else round(age, 1),
    }
