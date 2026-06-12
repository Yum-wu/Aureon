# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

Only the latest `main` branch receives security updates. Pin your deployments to the latest release.

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

- **Email**: [security@aureon.dev](mailto:security@aureon.dev)
- **Subject line**: `[SECURITY] <brief description>`
- **Response SLA**: We acknowledge receipt within **48 hours** and aim to provide a fix or mitigation within **7 days** for critical issues.

### What to Include

- Description of the vulnerability and its potential impact
- Steps to reproduce (if applicable)
- Any relevant logs, screenshots, or proof-of-concept code
- Your contact information for follow-up questions

### What to Expect

1. **Acknowledgment** ? We confirm receipt within 48 hours.
2. **Triage** ? We assess severity (Critical / High / Medium / Low) within 5 business days.
3. **Resolution** ? We develop and deploy a fix, coordinating disclosure with you.
4. **Credit** ? We acknowledge your contribution in our release notes (unless you prefer to remain anonymous).

## Security Best Practices

### API Key Management

- **Never** commit API keys to the repository. Use `.env` files (excluded via `.gitignore`) or your deployment platform's secret management.
- Rotate API keys immediately if you suspect they have been exposed.
- Use the `API_AUTH_KEY` environment variable to enable authentication on all `/api/` endpoints in production.
- Use the `JWT_SECRET` environment variable for JWT token signing (SSO/RBAC). Never use default or weak secrets.
- Use the `ENCRYPTION_KEY` environment variable for Fernet encryption of SSO secrets.

### Network Isolation

- In production, restrict Redis and Elasticsearch access to the application network only.
- The `QDRANT_API_KEY` environment variable should be set for Qdrant instances exposed beyond localhost.
- Use TLS/HTTPS for all production traffic (handled by Railway's edge proxy or your own reverse proxy).

### WebSocket Security

- WebSocket connections (`/ws/chat/{client_id}`) require the same authentication as REST endpoints.
- WebSocket heartbeat and timeout limits prevent resource exhaustion (`WEBSOCKET_HEARTBEAT_INTERVAL=30`, `WEBSOCKET_HEARTBEAT_TIMEOUT=300`).
- Maximum concurrent connections configurable via `WEBSOCKET_MAX_CONNECTIONS`.

### Container Security

- The Dockerfile runs the application as a non-root user (`appuser`) via `gosu`.
- Resource limits are configured in `docker-compose.yml` to prevent runaway processes.
- Do not run containers with `--privileged` or mount the Docker socket.

## Dependency Security

- Python dependencies are pinned to compatible version ranges in `backend/requirements.txt`.
- Frontend dependencies use `package-lock.json` for reproducible installs.
- Run `pip-audit` or `npm audit` periodically to check for known vulnerabilities:

  ```bash
  # Backend
  cd backend && pip-audit

  # Frontend
  npm audit
  ```

## Sensitive Data Handling

- Sensitive configuration values (SSO secrets, LLM API keys) are encrypted at rest via Fernet encryption (`backend/app/security/__init__.py`).
- Prompt Injection detection is implemented in `backend/app/rag/guardrails.py`.
- PII (Personally Identifiable Information) detection is implemented in `backend/app/security/`.

## Responsible Disclosure

Please do not publicly disclose vulnerabilities until we have had a reasonable opportunity to address them. We are committed to working with security researchers and will credit responsible disclosures.
