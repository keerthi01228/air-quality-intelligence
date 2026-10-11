# AIR — Air-quality Intelligence and Early-warning

**A serverless prototype for exploring air-quality risk assessment, alert escalation, and simulated early-warning workflows using AWS.**

## Overview

Air pollution can change quickly, and communities need timely, understandable information to help them respond. AIR explores how an air-quality early-warning workflow could process incoming observations, assess risk, manage alerts, and prepare actionable messages.

The project demonstrates this workflow through predefined scenarios, a web dashboard, and AWS-backed storage.

> **Important:** AIR is a prototype. Its current scenarios use simulated data, and its thresholds and messages are not official air-quality guidance. It does not currently provide verified, real-world public pollution warnings.

## Live Demo

- **Dashboard:** https://main.d8gw55mpqyaru.amplifyapp.com
- **API endpoint:** https://7hsvx2hnlcs6ko4bzp2zfhzjgm0rlxfn.lambda-url.ap-south-1.on.aws/
- **Source code:** https://github.com/keerthi01228/air-quality-intelligence

The demo is intended for exploration and demonstration. Public read endpoints are available, while write operations require operator-token authentication.

## Key Features

- **Scenario-based testing:** Explore normal conditions, gradually increasing risk, sudden severe conditions, persistent risk, conflicting or missing observations, recovery, and re-escalation.
- **Risk assessment:** Evaluate observations against prototype rules to determine risk states.
- **Alert lifecycle:** Demonstrate alert creation, escalation, authorization, message preparation, and simulated delivery.
- **Traceability:** Inspect event history and alert traces to understand how the workflow reached a decision.
- **Fallback and reliability tests:** Exercise missing-data handling, failure scenarios, and repeat-operation safeguards.
- **AWS-backed persistence:** Store application records in Amazon DynamoDB for the deployed demonstration.

## Architecture

AIR uses AWS serverless services to keep the prototype relatively simple to deploy and operate.

| Component | Purpose |
|---|---|
| AWS Amplify Hosting | Hosts the web dashboard |
| AWS Lambda | Runs the application and API logic |
| Lambda Function URL | Provides the HTTP API endpoint |
| Amazon DynamoDB | Stores application data |
| Amazon CloudWatch | Collects Lambda logs and monitoring information |
| AWS IAM | Controls permissions for AWS resource access |

### Simplified request flow

1. A user opens the dashboard.
2. The dashboard requests data from the Lambda API.
3. The application processes observations or a selected demonstration scenario.
4. Risk and alert logic evaluates the scenario.
5. Records are stored and retrieved through the configured storage layer.
6. The dashboard displays the resulting alerts, history, and traces.

## Testing

The local test suite was run successfully during development.

The reported tests covered:

- Eight predefined scenarios.
- Workflow authorization.
- Fallback behavior when AI-related processing fails.
- Simulated delivery.
- Idempotency and audit behavior.
- Storage parity using a simulated DynamoDB client.

These results demonstrate that the tested local workflows passed. They do **not** establish that every production scenario, external integration, or deployed AWS behavior has been independently verified.

## Repository Structure

```text
air-quality-intelligence/
├── air-engine/     # Core logic and scenario tests
├── air-frontend/   # Web dashboard
├── air-lambda/     # AWS Lambda application
└── air-repo/       # Supporting code and test package
```

## Security and Limitations

- The dashboard uses a public API endpoint for demonstration.
- Write operations use a shared operator token; this is prototype authentication, not a production identity-management system.
- Scenario observations are simulated rather than verified live sensor readings.
- Message delivery is demonstrated through the prototype workflow and should not be interpreted as a live public-warning broadcast.
- The system has not been validated for official emergency response, regulatory compliance, or real-world health decisions.
- Before production use, the project would require stronger authentication and authorization, abuse protection, operational monitoring, reliable real-world data sources, and independent validation.

## Future Improvements

Potential next steps include integrating trusted air-quality data sources, improving geographic risk assessment, supporting regional-language messages and audio, strengthening operator access controls, and evaluating reliable public-notification channels.

## Project Purpose

AIR is a learning and hackathon prototype exploring how cloud-based services can support a traceable, scenario-driven air-quality early-warning workflow. Its focus is on demonstrating the technical workflow while making the current system's limitations explicit.

