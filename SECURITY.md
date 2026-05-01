# Security Policy

## Supported versions

Free Games Notifier follows a rolling-release model: only the **latest published GHCR image tag** receives security updates. Older tagged versions are kept available for download but are not patched.

If you are pinning to a specific version (e.g. `ghcr.io/juliomoralesb/free-games-notifier:1.2.3`), please update to the latest tag promptly when a security release is announced.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.** Public disclosure before a fix is available exposes every self-hoster running the project.

### How to report

Use one of the following private channels:

1. **GitHub Security Advisory** (preferred) — go to the repo's [Security tab](https://github.com/JulioMoralesB/free-games-notifier/security/advisories/new) and click **Report a vulnerability**. This creates a private discussion thread visible only to you and the maintainer.
2. **Email** — send the details to <juliomoralesbd@gmail.com> with the subject line `[SECURITY] free-games-notifier`.

### What to include

- A clear description of the vulnerability and its potential impact
- Steps to reproduce, ideally with a minimal proof of concept
- The version (Git commit SHA or GHCR tag) affected
- Whether you would like public credit once the advisory is published

### What to expect

| Step | Timeline |
|---|---|
| Acknowledgement of receipt | Within **7 days** |
| Initial assessment + severity classification | Within **14 days** |
| Patch + coordinated disclosure plan | Depends on severity and complexity, typically 30 days for high-severity issues |

You will be kept in the loop throughout. If the issue turns out to be lower-severity than initially reported (e.g. requires already-compromised credentials), we will explain that reasoning rather than silently downgrade.

## Scope

Issues considered in scope:

- Authentication or authorization bypass on any REST endpoint
- Server-Side Request Forgery (SSRF) in webhook handling — we already validate Discord webhook URLs in `validate_discord_webhook_url`; bypasses of that validator are in scope
- SQL injection in the PostgreSQL backend
- Remote code execution via crafted scraper input or webhook payloads
- Path traversal in storage / log file handling
- Leaks of sensitive configuration (API keys, webhook URLs) via logs, error responses, or the dashboard
- Container escape from the published Docker image
- Vulnerable third-party dependencies that affect the running service

Issues considered out of scope:

- DoS via local resource exhaustion (we are a single-tenant home-server app)
- Issues requiring a malicious upstream (Epic Games or Steam returning crafted responses) — please report those to the upstream service
- Social engineering against the maintainer
- Reports generated entirely by automated scanners with no manual triage

## Hardening recommendations for self-hosters

The project's defaults are intentionally low-friction for home-server use. If you expose the service to the public internet, **please** apply the following:

- Set `API_KEY` to a strong random value; without it, all mutating endpoints are unauthenticated
- Put the service behind a reverse proxy with TLS (Caddy, Traefik, Cloudflare Tunnel)
- Restrict access to `/dashboard/`, `/check`, `/notify/discord/resend`, and `/config` to your home network or an authenticated tunnel; the dashboard reveals game history, the other endpoints can drain Discord rate limits
- Keep your PostgreSQL instance off the public internet; bind the service to `127.0.0.1` or a private Docker network

A future release (see milestone **Hybrid Configuration**) will surface these recommendations directly in the dashboard and warn when the service is reachable without authentication.

## Credit

We are happy to publicly credit reporters in the GitHub Security Advisory and the release notes. Let us know in your initial report whether you want credit and what name / handle to use.

Thanks for helping keep self-hosters safe.
