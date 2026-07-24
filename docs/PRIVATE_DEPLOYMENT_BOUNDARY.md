# LedgerMatch Private Deployment Boundary

## Scope

This document defines the boundary for private, local evaluation of
LedgerMatch v0.4.0. It explicitly states what the current implementation
does **not** provide.

## Allowed Deployments

### Local Machine

- Run LedgerMatch on the practitioner's local machine.
- Use loopback binding (`127.0.0.1` or `localhost`) for the web review
  interface.
- Store pilot data in a local directory excluded by `.gitignore`.

### Private Network (Restricted)

- Run LedgerMatch on a private server accessible only within a trusted
  network.
- Use an authenticated reverse proxy (e.g., nginx with client certificates
  or HTTP basic auth) in front of the LedgerMatch server.
- Bind the LedgerMatch server to `127.0.0.1` and let the proxy handle
  external access.

## Prohibited Deployments

### Public Internet

**Do not expose LedgerMatch directly to the public internet.**

The built-in Python HTTP server (`app/server.py`) provides:

- Host and Origin header enforcement.
- Local server shutdown.

It does **not** provide:

- **Authentication** — no login, session, or token-based auth.
- **Authorization** — no role-based access control or tenant isolation.
- **Encrypted persistent storage** — data is stored in plain files.
- **Retention enforcement** — no automatic data deletion or retention
  policy.
- **Upload malware scanning** — no virus scanning of uploaded files.
- **Backups** — no automatic backup or recovery mechanism.
- **Incident response** — no logging, alerting, or incident detection.

### Anonymous Public Upload

**Do not create an anonymous public file upload service.** LedgerMatch is
not designed to accept untrusted file uploads from the public internet.

## External Gates for Private Server Deployment

If a private server deployment is required, the following external gates
must be satisfied **before** deployment. These are **not** provided by
LedgerMatch and must be implemented externally:

### TLS

- Terminate TLS at the reverse proxy (nginx, Caddy, or equivalent).
- Use valid certificates (Let's Encrypt or internal CA).
- LedgerMatch itself runs plain HTTP behind the proxy.

### Identity

- Implement authentication at the proxy layer (HTTP basic auth, OAuth
  proxy, or client certificates).
- Each practitioner must have a unique identity.
- No anonymous access.

### Storage

- Store pilot data on encrypted volumes.
- Implement access controls at the filesystem level.
- Do not store data on shared network drives without encryption.

### Secrets

- Store API keys, database credentials, and private keys in a secrets
  manager (e.g., HashiCorp Vault, AWS Secrets Manager).
- Never store secrets in environment files committed to repositories.
- Rotate secrets regularly.

### Backup

- Implement automated backups of pilot data.
- Test backup restoration.
- Store backups encrypted, off-site or in a separate availability zone.

### Retention

- Define a data retention policy (e.g., 90 days after pilot completion).
- Implement automated deletion after the retention period.
- Document the retention policy in the pilot protocol.

### Monitoring

- Implement access logging at the proxy layer.
- Set up alerting for unauthorized access attempts.
- Monitor for data exfiltration patterns.

## Container Deployment

If containerizing LedgerMatch for private use:

- Use a minimal base image (e.g., `python:3.12-slim`).
- Run as a non-root user.
- Bind to `127.0.0.1` inside the container.
- Use Docker network isolation.
- Do not expose ports to the host's public interface.
- Mount pilot data as a read-write volume on an encrypted host filesystem.
- Do not bake secrets into the image.

## What This Document Is Not

- This is not a security audit.
- This is not a compliance certification.
- This is not a deployment guide for production.
- This is a boundary statement for private, local evaluation only.
