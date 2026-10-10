"""Tests the DynamoDB store (with a fake client) and the Lambda handler locally, no AWS needed."""
import json
import os
import sys

os.environ["OPERATOR_TOKEN"] = "test-token"
import lambda_function as lf                      # noqa: E402
from air.dynamo_store import DynamoStore          # noqa: E402
from air.service import AirService                # noqa: E402

FAILS = []


def check(cond, label):
    if not cond:
        FAILS.append(label)
        print("  FAIL:", label)


class FakeDynamoClient:
    """Minimal stand-in for boto3.client('dynamodb') with 2-item pages to exercise pagination."""
    def __init__(self):
        self.items = {}

    def put_item(self, TableName, Item):
        self.items[(Item["pk"]["S"], Item["sk"]["S"])] = Item

    def get_item(self, TableName, Key, ConsistentRead=False):
        it = self.items.get((Key["pk"]["S"], Key["sk"]["S"]))
        return {"Item": it} if it else {}

    def delete_item(self, TableName, Key):
        self.items.pop((Key["pk"]["S"], Key["sk"]["S"]), None)

    def query(self, TableName, KeyConditionExpression, ExpressionAttributeValues, ConsistentRead=False,
              ExclusiveStartKey=None):
        pk = ExpressionAttributeValues[":p"]["S"]
        keys = sorted(k for k in self.items if k[0] == pk)
        if ExclusiveStartKey:
            keys = [k for k in keys if k[1] > ExclusiveStartKey["sk"]["S"]]
        page = keys[:2]
        out = {"Items": [self.items[k] for k in page]}
        if len(keys) > 2:
            out["LastEvaluatedKey"] = {"pk": {"S": pk}, "sk": {"S": page[-1][1]}}
        return out


def scenario(name):
    with open(os.path.join("scenarios", name + ".json")) as fh:
        return json.load(fh)


def call(method, path, body=None, token="test-token"):
    event = {"requestContext": {"http": {"method": method}}, "rawPath": path,
             "headers": {"x-operator-token": token} if token else {}, "body": json.dumps(body) if body else None}
    r = lf.lambda_handler(event)
    return r["statusCode"], json.loads(r["body"]) if r["body"] else None


print("STORAGE PARITY (DynamoStore on a fake client vs in-memory)")
for name in ("C2_escalation", "E_missing_conflicting", "F2_reescalation"):
    data = scenario(name)
    mem, dyn = AirService(), AirService(store=DynamoStore(client=FakeDynamoClient()))
    a = [mem.ingest_cycle(c) for c in data["cycles"]]
    b = [dyn.ingest_cycle(c) for c in data["cycles"]]
    check([r["new_state"] for r in a] == [r["new_state"] for r in b], name + " states differ")
    check([x["alert_type"] for x in mem.alerts()] == [x["alert_type"] for x in dyn.alerts()], name + " alerts differ")
    check(len(mem.history()) == len(dyn.history()), name + " decision count differs")
    print("  %-24s %s" % (name, "PASS" if not FAILS else "FAIL"))

print("\nLAMBDA HANDLER (local, in-memory store)")
os.environ["AIR_STORE"] = "memory"
check(call("OPTIONS", "/status", token=None)[0] == 204, "OPTIONS preflight")
check(call("GET", "/")[0] == 200, "health")
check(call("POST", "/demo/reset", token="wrong")[0] == 401, "bad token rejected")
check(call("POST", "/demo/reset", token=None)[0] == 401, "missing token rejected")
check(call("POST", "/demo/reset")[0] == 200, "reset")
code, body = call("POST", "/demo/replay", {"scenario": "C2_escalation"})
check(code == 200 and body["simulated"] and len(body["results"]) == 6, "replay whole scenario")
code, st = call("GET", "/status")
check(code == 200 and st["state"] == "SEVERE" and st["data_label"] == "SIMULATED DEMO DATA", "status after replay")
code, alerts = call("GET", "/alerts")
check(code == 200 and len(alerts) == 2, "two alerts")
a1 = alerts[0]["alert_id"]
check(call("POST", "/alerts/%s/message" % a1, {})[0] == 403, "message blocked before approval")
check(call("POST", "/alerts/%s/authorize" % a1, {"action": "approve", "note": "ok"})[0] == 200, "approve")
check(call("POST", "/alerts/%s/authorize" % a1, {"action": "reject"})[0] == 400, "approved -> rejected refused")
code, msg = call("POST", "/alerts/%s/message" % a1, {})
check(code == 200 and msg["method"] == "TEMPLATE", "template message")
code, d = call("POST", "/alerts/%s/deliver" % a1, {"channel": "MOCK_CBS"})
check(code == 200 and d["status"] == "SUBMITTED_SIMULATED", "simulated delivery")
code, tr = call("GET", "/alerts/%s/trace" % a1)
check(code == 200 and tr["complete"], "trace complete")
check(call("GET", "/alerts/ALR-9999/trace")[0] == 404, "unknown alert 404")
check(call("POST", "/demo/replay", {"scenario": "../etc/passwd"})[0] == 400, "scenario name validated")
code, st = call("GET", "/status")
check(st["state"] == "SEVERE", "state unchanged by authorization/delivery")
print("  handler checks done")

print("\nRESULT:", "ALL PASSED" if not FAILS else "%d FAILURE(S)" % len(FAILS))
sys.exit(1 if FAILS else 0)
