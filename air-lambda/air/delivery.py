"""Module 9 - Alert distribution (SIMULATED). No real SMS, SACHET or Cell Broadcast is used."""
from .validation import iso

CHANNELS = ("DASHBOARD", "MOCK_SMS", "MOCK_CBS")


def deliver(alert, message, channel, existing, at, simulate_failure=False):
    """Idempotent: one delivery record per alert and channel. Retries never create a new alert."""
    if channel not in CHANNELS:
        raise ValueError("Unknown channel %r" % channel)
    if alert["authorization_status"] != "APPROVED":
        raise PermissionError("Alert %s is not authorized for delivery" % alert["alert_id"])
    if message is None:
        raise ValueError("No message has been generated for this alert")
    rec = existing or {"delivery_id": "DLV-%s-%s" % (alert["alert_id"], channel), "alert_id": alert["alert_id"],
                       "message_id": message["message_id"], "channel": channel, "attempts": 0,
                       "history": [], "simulated": True, "status": None}
    if rec["status"] == "SUBMITTED_SIMULATED":
        return rec, False
    rec["attempts"] += 1
    rec["message_id"] = message["message_id"]
    rec["status"] = "FAILED_SIMULATED" if simulate_failure else "SUBMITTED_SIMULATED"
    rec["history"].append({"attempt": rec["attempts"], "status": rec["status"], "at": iso(at)})
    return rec, True
