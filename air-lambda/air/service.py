"""AirService - orchestrates the AIR pipeline. This is what the Lambda handler will wrap.

observations -> validation -> event signal -> risk state -> affected area -> alert decision
-> authorization -> message -> (simulated) delivery, with an audit trail at every step.
"""
import copy

from . import alerts as alerts_mod
from . import area as area_mod
from . import delivery as delivery_mod
from . import events, messages, risk
from .config import STATIONS, ZONES, get_config
from .store import InMemoryStore
from .validation import iso, parse_ts, validate_observation


def _initial_state():
    return {"state": "NORMAL", "counters": risk.new_counters(), "event_id": None, "event_seq": 0,
            "transition_seq": 0, "decision_seq": 0, "alert_seq": 0, "auth_seq": 0, "message_seq": 0,
            "audit_seq": 0, "last_obs": {}, "last_alert_zones": [], "alert_keys": [], "entered_from": "NORMAL",
            "last_as_of": None, "last_decision_id": None, "last_cycle_id": None}


class AirService:
    def __init__(self, store=None, cfg=None, stations=None, zones=None):
        self.store = store or InMemoryStore()
        self.cfg = cfg or get_config()
        self.stations = stations or STATIONS
        self.zones = zones or ZONES
        if self.store.state is None:
            self.store.state = _initial_state()

    # ------------------------------------------------------------------ audit
    def _audit(self, st, kind, actor, at, **fields):
        st["audit_seq"] += 1
        rec = {"audit_id": "AUD-%05d" % st["audit_seq"], "kind": kind, "actor": actor, "at": at,
               "policy_version": self.cfg["policy_version"]}
        rec.update(fields)
        self.store.put("audit", rec["audit_id"], rec)

    # ----------------------------------------------------------------- ingest
    def ingest_cycle(self, cycle):
        """Process one evaluation cycle (a batch of observations at time as_of). Idempotent per cycle_id."""
        cfg, cid = self.cfg, cycle["cycle_id"]
        prior = self.store.get("cycles", cid)
        if prior is not None:
            out = copy.deepcopy(prior)
            out["duplicate"] = True
            return out

        as_of = parse_ts(cycle["as_of"])
        as_of_s = iso(as_of)
        st = copy.deepcopy(self.store.state)
        prev = st["state"]

        # 1. store raw observations and assess their quality
        quality, fresh, sources = [], {}, set()
        for i, obs in enumerate(cycle.get("observations") or []):
            oid = obs.get("observation_id") or "%s-obs%d" % (cid, i + 1)
            raw = dict(obs)
            raw["observation_id"], raw["cycle_id"] = oid, cid
            if self.store.get("observations", oid) is None:
                self.store.put("observations", oid, raw)
            q = validate_observation(raw, as_of, cfg, self.stations)
            q["cycle_id"] = cid
            self.store.put("quality", "%s:%s" % (cid, oid), q)
            quality.append(q)
            if q["status"] == "VALID":
                sid, ts = raw["station_id"], parse_ts(raw["timestamp"])
                sources.add(str(raw.get("source", "UNKNOWN")))
                if sid not in fresh or ts > fresh[sid][0]:
                    fresh[sid] = (ts, raw)

        # 2. snapshot: fresh reading, else carried forward while still fresh enough, else missing
        usable, missing = {}, []
        for sid in self.stations:
            if sid in fresh:
                ts, raw = fresh[sid]
                usable[sid] = {"aqi": float(raw["aqi"]), "observation_id": raw["observation_id"],
                               "timestamp": iso(ts), "carried": False}
                st["last_obs"][sid] = {"observation_id": raw["observation_id"], "timestamp": iso(ts),
                                       "aqi": float(raw["aqi"]), "source": str(raw.get("source", "UNKNOWN"))}
            else:
                last = st["last_obs"].get(sid)
                if last and (as_of - parse_ts(last["timestamp"])).total_seconds() / 60.0 <= cfg["stale_minutes"]:
                    usable[sid] = {"aqi": last["aqi"], "observation_id": last["observation_id"],
                                   "timestamp": last["timestamp"], "carried": True}
                    sources.add(last.get("source", "UNKNOWN"))
                else:
                    missing.append(sid)
        coverage = len(usable) / len(self.stations)
        carried = sum(1 for u in usable.values() if u["carried"])
        carried_share = carried / len(usable) if usable else 0.0
        label = "SIMULATED DEMO DATA" if any(s.upper().startswith("SIM") for s in sources) else "Source data as ingested"

        # 3. evidence signal and risk state
        signal = events.detect_signal(usable, cfg, self.stations)
        res = risk.assess(prev, st["counters"], signal, coverage, carried_share, cfg)
        new = res["new_state"]
        if new != prev:
            st["transition_seq"] += 1
            st["entered_from"] = prev

        # 4. event lifecycle
        if st["event_id"] is None and new != "NORMAL":
            event = events.open_event(st, as_of)
        elif st["event_id"]:
            event = copy.deepcopy(self.store.get("events", st["event_id"]))
        else:
            event = None
        event_id = event["event_id"] if event else None

        # 5. affected area (never claims more than the evidence supports)
        if res["sufficient"]:
            area = area_mod.compute_area(usable, signal, cfg, self.stations, self.zones)
            if not area["zones"] and new != "NORMAL" and event and event["last_area"]:
                area = area_mod.carry(event["last_area"], "Carried from the previous cycle: evidence below threshold this cycle.")
        else:
            area = area_mod.carry(event["last_area"] if event else None,
                                  "Carried from the last cycle with sufficient data: not enough stations are reporting.")
        st["decision_seq"] += 1
        decision_id = "DEC-%04d" % st["decision_seq"]
        area_id = "AREA-%04d" % st["decision_seq"]
        area["confidence"] = res["confidence"]
        area["area_id"], area["decision_id"] = area_id, decision_id

        evidence = area["evidence_refs"] or sorted(u["observation_id"] for u in usable.values())
        decision = {
            "decision_id": decision_id, "cycle_id": cid, "as_of": as_of_s, "event_id": event_id,
            "previous_state": prev, "new_state": new, "changed": new != prev,
            "candidate_level": signal["candidate"], "reason_codes": res["codes"], "reason": res["reason"],
            "confidence": res["confidence"], "data_sufficient": res["sufficient"], "coverage": round(coverage, 2),
            "evidence_refs": evidence, "affected_zones": area["zones"], "area_id": area_id,
            "counters": res["counters"], "policy_version": cfg["policy_version"], "thresholds": cfg["thresholds"],
            "data_label": label,
            "snapshot": {"usable": usable, "missing": missing,
                         "invalid": sorted(q["observation_id"] for q in quality if q["status"] == "INVALID"),
                         "stale": sorted(q["observation_id"] for q in quality if q["status"] == "STALE")},
            "signal": {k: signal[k] for k in ("candidate", "min_stations", "usable_count", "over_counts",
                                              "strong_severe", "uncorroborated_spikes", "conflict_zones")},
        }
        st["state"], st["counters"] = new, res["counters"]
        st["last_as_of"], st["last_cycle_id"], st["last_decision_id"] = as_of_s, cid, decision_id
        self.store.put("decisions", decision_id, decision)
        self.store.put("areas", area_id, area)
        self._audit(st, "RISK_DECISION", "engine", as_of_s, decision_id=decision_id, event_id=event_id,
                    previous_state=prev, new_state=new, reason=res["reason"], evidence_refs=evidence)

        # 6. alert decision (kept separate from the risk state)
        if event:
            events.update_event(event, decision, area, as_of)
        alert_dec = alerts_mod.decide_alert(new, decision, area, st, cfg)
        alert_id = None
        if alert_dec["decision"] == "ALERT_REQUIRED":
            facts = messages.build_facts(new, alert_dec["alert_type"], decision, area, cfg, self.zones, label)
            alert = alerts_mod.build_alert(st, event_id, decision, area, facts, as_of,
                                           alert_dec["alert_type"], alert_dec["dedupe_key"])
            alert_id = alert["alert_id"]
            st["alert_keys"].append(alert_dec["dedupe_key"])
            st["last_alert_zones"] = list(area["zones"])
            self.store.put("alerts", alert_id, alert)
            self._audit(st, "ALERT_CREATED", "engine", as_of_s, alert_id=alert_id, decision_id=decision_id,
                        reason=alert_dec["reason"])
        else:
            self._audit(st, "NO_ALERT", "engine", as_of_s, decision_id=decision_id, code=alert_dec["code"],
                        reason=alert_dec["reason"])

        if event and new == "NORMAL":
            events.close_event(event, as_of)
            st["event_id"] = None
            st["last_alert_zones"] = []
        if event:
            self.store.put("events", event["event_id"], event)

        result = {"cycle_id": cid, "as_of": as_of_s, "duplicate": False, "previous_state": prev, "new_state": new,
                  "decision_id": decision_id, "event_id": event_id, "alert_decision": alert_dec["decision"],
                  "alert_code": alert_dec["code"], "alert_reason": alert_dec["reason"], "alert_id": alert_id,
                  "reason_codes": res["codes"], "confidence": res["confidence"], "coverage": round(coverage, 2),
                  "data_sufficient": res["sufficient"], "invalid_observations": decision["snapshot"]["invalid"]}
        self.store.put("cycles", cid, result)
        self.store.state = st
        return copy.deepcopy(result)

    # ------------------------------------------------------------ read models
    def status(self):
        st = self.store.state
        dec = self.store.get("decisions", st["last_decision_id"]) if st["last_decision_id"] else None
        ev = self.store.get("events", st["event_id"]) if st["event_id"] else None
        label = st["state"]
        if dec and not dec["data_sufficient"]:
            label += " (HELD - insufficient data, not confirmed clean)"
        elif st["state"] == "RECOVERY":
            label += " (improving - not an all-clear)"
        readings = []
        if dec:
            for sid, s in self.stations.items():
                u = dec["snapshot"]["usable"].get(sid)
                readings.append({"station_id": sid, "name": s["name"], "zone": s["zone"], "lat": s["lat"],
                                 "lon": s["lon"], "aqi": u["aqi"] if u else None,
                                 "carried_forward": bool(u and u["carried"]), "missing": u is None})
        area = self.store.get("areas", dec["area_id"]) if dec else None
        return {"state": st["state"], "state_label": label, "as_of": st["last_as_of"],
                "decision": dec, "event": ev, "affected_area": area, "readings": readings,
                "pending_alerts": [a for a in self.alerts() if a["authorization_status"] == "PENDING"],
                "policy_version": self.cfg["policy_version"], "data_label": dec["data_label"] if dec else None}

    def events(self):
        return sorted(self.store.values("events"), key=lambda e: e["event_id"])

    def alerts(self):
        return sorted(self.store.values("alerts"), key=lambda a: a["alert_id"])

    def history(self):
        return sorted(self.store.values("decisions"), key=lambda d: d["decision_id"])

    # --------------------------------------------------------- authorization
    def authorize(self, alert_id, action, operator, note="", at=None):
        st = self.store.state
        alert = self._alert(alert_id)
        at_dt = parse_ts(at) if at else parse_ts(st["last_as_of"])
        st["auth_seq"] += 1
        rec = alerts_mod.authorize(alert, action, operator, note, at_dt, st["auth_seq"], self.cfg["policy_version"])
        alert["authorization_status"] = rec["to"]
        if rec["to"] == "APPROVED" and alert["message_id"]:
            alert["delivery_status"] = "READY"
        self.store.put("authorizations", rec["authorization_id"], rec)
        self._audit(st, "AUTHORIZATION", operator, rec["at"], alert_id=alert_id,
                    authorization_id=rec["authorization_id"], new_status=rec["to"], note=note)
        self.store.put("alerts", alert_id, alert)
        self.store.save_state()
        return rec

    # --------------------------------------------------------------- message
    def generate_message(self, alert_id, ai_fn=None, at=None):
        st = self.store.state
        alert = self._alert(alert_id)
        if alert["authorization_status"] != "APPROVED":
            raise PermissionError("Alert %s must be APPROVED before a message is generated" % alert_id)
        out = messages.generate_message(alert["facts"], ai_fn)
        st["message_seq"] += 1
        version = 1 + sum(1 for m in self.store.values("messages") if m["alert_id"] == alert_id)
        rec = {"message_id": "MSG-%04d" % st["message_seq"], "alert_id": alert_id, "version": version,
               "text": out["text"], "method": out["method"], "problems": out["problems"],
               "fallback_reason": out["fallback_reason"], "created_at": at or st["last_as_of"]}
        self.store.put("messages", rec["message_id"], rec)
        alert["message_id"], alert["delivery_status"] = rec["message_id"], "READY"
        self._audit(st, "MESSAGE_GENERATED", "engine", rec["created_at"], alert_id=alert_id,
                    message_id=rec["message_id"], method=out["method"], fallback_reason=out["fallback_reason"])
        self.store.put("alerts", alert_id, alert)
        self.store.save_state()
        return rec

    # -------------------------------------------------------------- delivery
    def deliver(self, alert_id, channel="DASHBOARD", simulate_failure=False, at=None):
        st = self.store.state
        alert = self._alert(alert_id)
        message = self.store.get("messages", alert["message_id"]) if alert["message_id"] else None
        at_dt = parse_ts(at) if at else parse_ts(st["last_as_of"])
        existing = self.store.get("deliveries", "DLV-%s-%s" % (alert_id, channel))
        rec, changed = delivery_mod.deliver(alert, message, channel, existing, at_dt, simulate_failure)
        self.store.put("deliveries", rec["delivery_id"], rec)
        alert["delivery_status"] = rec["status"]       # delivery never touches the risk state
        if changed:
            self._audit(st, "DELIVERY", "delivery-adapter", iso(at_dt), alert_id=alert_id,
                        delivery_id=rec["delivery_id"], status=rec["status"], attempt=rec["attempts"])
        self.store.put("alerts", alert_id, alert)
        self.store.save_state()
        return rec

    # ----------------------------------------------------------------- trace
    def trace(self, alert_id):
        """Rebuild the evidence chain behind one alert."""
        alert = self._alert(alert_id)
        dec = self.store.get("decisions", alert["decision_id"])
        refs = set(dec["evidence_refs"])
        chain = {
            "alert": alert, "decision": dec,
            "policy_version": dec["policy_version"],
            "event": self.store.get("events", alert["event_id"]),
            "affected_area": self.store.get("areas", dec["area_id"]),
            "observations": [self.store.get("observations", o) for o in sorted(refs)],
            "data_quality": [q for q in self.store.values("quality") if q["observation_id"] in refs],
            "authorizations": [a for a in self.store.values("authorizations") if a["alert_id"] == alert_id],
            "messages": [m for m in self.store.values("messages") if m["alert_id"] == alert_id],
            "deliveries": [d for d in self.store.values("deliveries") if d["alert_id"] == alert_id],
        }
        chain["complete"] = all([chain["event"], chain["affected_area"], chain["observations"],
                                 chain["data_quality"], chain["authorizations"], chain["messages"],
                                 chain["deliveries"], chain["policy_version"]])
        return chain

    def _alert(self, alert_id):
        alert = self.store.get("alerts", alert_id)
        if alert is None:
            raise KeyError("Unknown alert %s" % alert_id)
        return alert
