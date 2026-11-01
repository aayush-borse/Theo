# Security policy

## Supported deployment posture

The local launcher binds to `127.0.0.1` and is intended for development. Docker Compose enables API authentication and role restrictions, uses PostgreSQL and Redis, and runs a separate worker. Neither profile is a substitute for a deployment security review.

## Account and token security

- Passwords are hashed with salted scrypt; plaintext passwords are never stored.
- Bearer tokens are signed with HS256 and expire after one hour.
- Set `THEO_JWT_SECRET` to a cryptographically random value of at least 32 characters. Never commit `.env` or share the secret.
- The first account becomes administrator. Further accounts are provisioned by an administrator via `POST /api/auth/users`.
- Roles: `admin`, `reviewer`, `viewer`. Viewers are read-only; reviewers can process/review; administrators can delete and publish releases.
- Do not set `THEO_ALLOW_SELF_REGISTER=true` on an exposed deployment.

## Upload handling

THEO enforces a per-file size limit, extension allowlist per modality and SHA-256 deduplication. These controls do not constitute malware scanning, archive-bomb protection or content disarm/reconstruction. Treat uploads as untrusted. Deploy with restricted filesystem permissions, antivirus scanning where appropriate, request/body limits and isolated workers.

## Production checklist

- HTTPS and hardened reverse proxy; restrict CORS origins.
- Unique secrets via a secret manager; rotate secrets and database credentials.
- Non-default PostgreSQL password; private database and Redis networks.
- Upload scanning, content validation and retention/deletion policy.
- Least-privilege service accounts and filesystem/object-store ACLs.
- Database and asset backups with restore drills.
- Dependency, container and model supply-chain scanning.
- Worker CPU/memory/GPU limits, queue monitoring and retry/dead-letter policy.
- Audit retention and external tamper-evident archival if compliance requires it.
- Privacy, consent, model licence and data residency review before external inference.

## Reporting vulnerabilities

Do not disclose exploitable vulnerabilities publicly before maintainers have had a reasonable opportunity to investigate. Provide reproduction steps, affected version, impact and suggested mitigation through the repository's private security reporting channel.
