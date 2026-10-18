# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | ✅ Supported       |

## Security Model

This tool is designed to run **locally** on your own machine (`localhost:3003` by default, or `0.0.0.0:3003` if you want LAN access). All data (CCASS holdings, trading data, shareholder registers) is stored in a local SQLite database under `data/`. **No data is sent to any cloud server** except public data sources (HKEX, Tencent Finance, Yahoo Finance) for fetching market data.

### What this means for security:
- No login/authentication is required because the app is intended for single-user local use
- API keys (LLM, webhook) are stored locally in `backend/config.json` and never logged or exposed in full to the frontend
- Uploaded files are saved under `uploads/` with UUID-prefixed sanitized filenames (path traversal is prevented)

## ⚠️ Deployment Warning

**Do NOT expose this application directly to the public internet** (e.g., behind a reverse proxy on a VPS without authentication). The app has no built-in authentication or rate limiting, and is not designed for multi-user or public deployment. It is a local desktop/server tool for personal use.

If you need remote access, use SSH tunneling or a VPN rather than exposing port 3003 directly.

## Reporting Vulnerabilities

If you discover a security vulnerability, please **do not** open a public GitHub issue. Instead, report it privately via:

- GitHub Security Advisory: [Report a vulnerability](https://github.com/stevenshi-vibe/hk-stock-panel/security/advisories/new)
- Or open a [private issue](https://github.com/stevenshi-vibe/hk-stock-panel/issues/new) with "SECURITY:" prefix

I will respond as quickly as possible and work with you to resolve the issue before public disclosure.

## Known Security Considerations

1. **No authentication** — intentional for local use; do not deploy publicly
2. **CORS allows all origins** (`*`) — safe for localhost; restrict if you change the host binding
3. **File uploads** — filename sanitization is applied to prevent path traversal; accepted extensions are limited to `.xlsx`, `.xls`, `.csv`, `.pdf`, `.txt`, `.tsv`
4. **LLM API keys** — masked in API responses (first 8 + last 4 chars shown in settings UI)
5. **Dependencies** — Python and JS dependencies are pinned; check for updates periodically

## Data Privacy

- All stock data, shareholder registers, and uploaded files stay on your local machine
- LLM API calls (if enabled) send only report text content to your configured LLM provider — no authentication tokens or personal data are sent
- No telemetry, no analytics, no tracking of any kind
