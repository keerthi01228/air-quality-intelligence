"""Module 4 - Affected-area engine. The map only DISPLAYS this; the engine decides it.

Zone-level estimate built from corroborated observations. It is not a scientific
dispersion model and the output says so (precision = zone-level estimate).
"""
import copy
import math


def circle_polygon(lat, lon, radius_km, n=24):
    pts = []
    for i in range(n + 1):
        ang = 2 * math.pi * i / n
        dlat = (radius_km / 111.32) * math.cos(ang)
        dlon = (radius_km / (111.32 * math.cos(math.radians(lat)))) * math.sin(ang)
        pts.append([round(lon + dlon, 6), round(lat + dlat, 6)])
    return pts


def empty_area():
    return {"zones": [], "zone_levels": {}, "precision": "zone-level estimate", "evidence_refs": [],
            "signature": "", "geojson": {"type": "FeatureCollection", "features": []},
            "note": None, "confidence": None}


def compute_area(usable, signal, cfg, stations, zones):
    area = empty_area()
    if signal["candidate"] == "NORMAL":
        return area            # nothing corroborated, so no affected area is claimed
    thr = cfg["thresholds"]["elevated"]
    levels, evidence = {}, []
    for sid, u in usable.items():
        if u["aqi"] >= thr:
            z = stations[sid]["zone"]
            levels[z] = max(levels.get(z, 0), u["aqi"])
            evidence.append(u["observation_id"])
    area["zones"] = sorted(levels)
    area["zone_levels"] = {z: levels[z] for z in sorted(levels)}
    area["evidence_refs"] = sorted(evidence)
    area["signature"] = "|".join(area["zones"])
    for z in area["zones"]:
        zone = zones[z]
        area["geojson"]["features"].append({
            "type": "Feature",
            "properties": {"zone": z, "name": zone["name"], "max_aqi": levels[z]},
            "geometry": {"type": "Polygon",
                         "coordinates": [circle_polygon(zone["lat"], zone["lon"], cfg["zone_radius_km"])]},
        })
    return area


def carry(area, note):
    """Reuse the last known area when this cycle cannot support a fresh one."""
    out = copy.deepcopy(area) if area else empty_area()
    out["note"] = note
    return out
