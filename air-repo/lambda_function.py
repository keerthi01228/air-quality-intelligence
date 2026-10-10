"""AWS Lambda entry point for AIR (API Gateway HTTP API, payload format 2.0).

Environment variables:
    TABLE_NAME      DynamoDB table (default air-data)
    OPERATOR_TOKEN  shared secret for write endpoints (DEMO authentication, not production identity)
    AIR_STORE       set to 'memory' only for local testing
"""
import base64
import hmac
import json
import os
import re
import traceback

from air.service import AirService
from air.store import InMemoryStore

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIO_DIR = os.path.join(HERE, "scenarios")
CORS = {"access-control-allow-origin": "*",
        "access-control-allow-headers": "content-type,x-operator-token",
        "access-control-allow-methods": "GET,POST,OPTIONS"}

_client = None
_memory_store = InMemoryStore()


def _store():
    global _client
    if os.environ.get("AIR_STORE") == "memory":
        return _memory_store
    from air.dynamo_store import DynamoStore
    if _client is None:
        import boto3
        _client = boto3.client("dynamodb")
    return DynamoStore(client=_client)


def _resp(code, body=None):
    headers = dict(CORS)
    headers["content-type"] = "application/json"
    return {"statusCode": code, "headers": headers, "body": json.dumps(body if body is not None else {})}


def _is_operator(headers):
    expected = os.environ.get("OPERATOR_TOKEN", "")
    given = headers.get("x-operator-token", "")
    return bool(expected) and hmac.compare_digest(expected, given)


def _scenario(name):
    if not re.fullmatch(r"[A-Za-z0-9_]+", name or ""):
        raise ValueError("Invalid scenario name")
    path = os.path.join(SCENARIO_DIR, name + ".json")
    if not os.path.exists(path):
        raise KeyError("Unknown scenario " + name)
    with open(path) as fh:
        return json.load(fh)


def lambda_handler(event, context=None):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET").upper()
    path = (event.get("rawPath") or "/").rstrip("/") or "/"
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": CORS, "body": ""}
    try:
        body = {}
        if event.get("body"):
            raw = event["body"]
            if event.get("isBase64Encoded"):
                raw = base64.b64decode(raw).decode("utf-8")
            body = json.loads(raw)
        svc = AirService(store=_store())

        # ---- public read endpoints
        if method == "GET":
            if path == "/":
                return _resp(200, {"service": "AIR", "policy_version": svc.cfg["policy_version"],
                                   "note": "Prototype. Demo data is SIMULATED; thresholds are not official."})
            if path == "/status":
                return _resp(200, svc.status())
            if path == "/events":
                return _resp(200, svc.events())
            if path == "/alerts":
                return _resp(200, svc.alerts())
            if path == "/history":
                return _resp(200, svc.history())
            if path == "/scenarios":
                names = sorted(f[:-5] for f in os.listdir(SCENARIO_DIR) if f.endswith(".json"))
                return _resp(200, [{"name": n, "description": _scenario(n)["description"],
                                    "cycles": len(_scenario(n)["cycles"])} for n in names])
            m = re.fullmatch(r"/alerts/(ALR-\d+)/trace", path)
            if m:
                return _resp(200, svc.trace(m.group(1)))
            return _resp(404, {"error": "not found"})

        # ---- write endpoints need the operator token (demo authentication)
        if method == "POST":
            if not os.environ.get("OPERATOR_TOKEN"):
                return _resp(503, {"error": "OPERATOR_TOKEN is not configured"})
            if not _is_operator(headers):
                return _resp(401, {"error": "operator token required"})
            if path == "/cycles":
                return _resp(200, svc.ingest_cycle(body))
            if path == "/demo/reset":
                store = svc.store
                store.reset()
                return _resp(200, {"reset": True})
            if path == "/demo/replay":
                data = _scenario(body.get("scenario"))
                last = int(body.get("through") or body.get("cycle") or len(data["cycles"]))
                if body.get("cycle") and not body.get("through"):
                    results = [svc.ingest_cycle(data["cycles"][last - 1])]
                else:
                    results = [svc.ingest_cycle(c) for c in data["cycles"][:last]]
                return _resp(200, {"scenario": data["name"], "simulated": True, "results": results})
            m = re.fullmatch(r"/alerts/(ALR-\d+)/(authorize|message|deliver)", path)
            if m:
                alert_id, action = m.groups()
                if action == "authorize":
                    return _resp(200, svc.authorize(alert_id, str(body.get("action", "")).upper(),
                                                    body.get("operator") or "operator-demo", body.get("note", "")))
                if action == "message":
                    return _resp(200, svc.generate_message(alert_id))
                return _resp(200, svc.deliver(alert_id, body.get("channel", "DASHBOARD"),
                                              bool(body.get("simulate_failure"))))
            return _resp(404, {"error": "not found"})
        return _resp(405, {"error": "method not allowed"})
    except PermissionError as exc:
        return _resp(403, {"error": str(exc)})
    except KeyError as exc:
        return _resp(404, {"error": str(exc).strip("'\"")})
    except (ValueError, json.JSONDecodeError) as exc:
        return _resp(400, {"error": str(exc)})
    except Exception:                                   # logged to CloudWatch
        traceback.print_exc()
        return _resp(500, {"error": "internal error"})
