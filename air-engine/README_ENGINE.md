# AIR decision engine (prototype)

The decision core of AIR: validated observations -> pollution event -> affected area -> risk state ->
alert decision -> authorization -> message -> simulated delivery, with an audit trail at every step.
Plain Python (standard library only), no AWS needed to run or test it.

**Honesty notes:** all demo data is SIMULATED and labelled so. Thresholds are PROTOTYPE rules, not official
CPCB/NDMA values. Delivery (SMS, Cell Broadcast, SACHET) is mocked and never claimed as real.

## Run the tests
    python3 run_tests.py

Runs 8 repeatable scenarios (normal, gradual, sudden severe, escalation, persistent, missing/conflicting data,
recovery, re-escalation) plus workflow tests: authorization hold/reject, AI failure fallback, delivery failure
and retry, duplicate-cycle idempotency, and the full audit trace.

## Layout
| File | Spec module | Becomes on AWS |
|---|---|---|
| `air/validation.py` | Data validation & quality | inside the Lambda |
| `air/events.py` | Pollution event engine | inside the Lambda |
| `air/area.py` | Affected-area engine | inside the Lambda |
| `air/risk.py` | Risk state engine | inside the Lambda |
| `air/alerts.py` | Alert decision + authorization | inside the Lambda |
| `air/messages.py` | Message engine (template + AI validation) | Lambda (+ Bedrock later) |
| `air/delivery.py` | Distribution (simulated) | inside the Lambda |
| `air/store.py` | Alert state & history | DynamoDB tables (same API) |
| `air/service.py` | Orchestration + public read models | Lambda handler wraps this |
| `air/config.py` | Policy / thresholds | Parameter Store |

## Key rules enforced (and tested)
- Missing data never means clean air: coverage below 50% holds the current state.
- One abnormal reading never raises a regional warning (corroboration across stations is required).
- The same state does not re-alert; only meaningful change creates an alert (deduplicated by a stable key).
- RECOVERY is never an automatic all-clear; re-escalation is possible.
- Authorization, message generation and delivery are separate from the risk decision and never change it.
- AI drafts are checked against the approved facts and fall back to a template if they drift or fail.
