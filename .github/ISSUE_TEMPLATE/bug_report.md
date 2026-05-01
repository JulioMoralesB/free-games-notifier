---
name: Bug report
about: Something isn't working as expected
title: ""
labels: bug
assignees: ""
---

## Summary

<!-- One sentence: what is broken? -->

## Steps to reproduce

1.
2.
3.

## Expected behaviour

<!-- What did you expect to happen? -->

## Actual behaviour

<!-- What happened instead? Include relevant log lines (set ENABLE_HEALTHCHECK=false if logs are noisy). -->

```text
<paste relevant log lines here — redact webhook tokens, DB credentials, etc.>
```

## Environment

- **Version**: <!-- e.g. ghcr.io/juliomoralesb/free-games-notifier:1.2.3 — find it via `docker inspect` or look at the running tag -->
- **Deployment**: <!-- Docker Compose / standalone Docker / running from source -->
- **Storage backend**: <!-- PostgreSQL / JSON file -->
- **Region / TIMEZONE / LOCALE**: <!-- as set in your .env -->
- **Enabled stores**: <!-- e.g. epic,steam -->
- **OS / Architecture**: <!-- e.g. Ubuntu 24.04 amd64, Raspberry Pi OS arm64 -->

## Additional context

<!-- Screenshots, related issues, anything else that helps. -->
