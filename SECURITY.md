# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private reporting: in this repository, open **Security > Report a vulnerability**. Include the steps to reproduce, the impact, and the affected version. Use test data rather than real inspection images. This is a portfolio-stage project maintained on a best-effort basis, so response times can't be guaranteed.

## Principles

- The server enforces everything. The frontend is never trusted for permissions or validation.
- Uploaded files are hostile until proven otherwise.
- Errors tell users what to do, and never reveal internals.
- Secrets exist only in server environment variables.

## Authentication

- Passwords are hashed with Argon2id, with a 10-character minimum.
- Login failures look identical whether or not the account exists, and unknown e-mails still run a hash verification to reduce timing differences.
- JWT access tokens (HS256) carry a version number. Logging out or changing a password invalidates all of the account's tokens.
- Production refuses to start with a default or short `SECRET_KEY`.
- Login attempts are limited per IP and per e-mail address.

**Trade-off:** the frontend keeps its token in `sessionStorage`, where a successful script injection could read it. The app avoids `dangerouslySetInnerHTML`, and the deployment applies a strict Content-Security-Policy. The token is not stored in a cookie, so CSRF does not apply.

## File upload security

| Threat | Control |
|---|---|
| Malicious or disguised files | Extension allow-list, magic-byte check, extension must match content, and a full decode by Pillow |
| Oversized files | Reads stop one byte past the limit, and requests with oversized declared lengths are rejected early |
| Decompression bombs | Pixel count is checked from the header before decoding, and Pillow's bomb protection is treated as an error |
| Corrupt or animated files | Refused with a clear message |
| Path traversal and unsafe names | Storage names are generated. The sanitised filename is used for display only, and keys must match a strict pattern |
| Active content | SVG and HTML are refused. Files are served with `nosniff` and a restrictive Content-Security-Policy |
| Unauthorised access | Every file request checks ownership. Storage is not publicly served |

## Image privacy

- Original uploads are stored unchanged and are only downloadable by their owner, as an attachment.
- Display copies, thumbnails, processed images and reports have no EXIF, so no GPS data reaches reports.
- EXIF values are never stored. Only whether EXIF or GPS existed is kept, and the UI warns the owner when an original contains GPS.
- **Be aware:** because originals stay unchanged, any EXIF in them remains on disk until you delete them.

## Secret management

- `.env` is ignored by Git. `.env.example` holds placeholders only.
- `render.yaml` uses generated values and dashboard prompts, never literal secrets.
- Nothing in `VITE_` variables is secret, because they are compiled into public JavaScript.
- If a secret is ever committed, deleting the file is not enough: **rotate it**, then clean the history.

## Database protection

- All queries go through SQLAlchemy with bound parameters. Search input escapes `LIKE` wildcards.
- Every tenant query filters by ownership.
- Use a dedicated database user, TLS and restricted network access in production. Render's `ipAllowList` can limit external access.

## API security

- CORS allows explicit origins only, and production refuses a wildcard. Credentials mode is off.
- Security headers are set on all responses, with HSTS in production.
- Validation errors never echo submitted values.
- Unhandled errors return a generic message, with details only in server logs.
- API documentation is off by default in production.
- Requests are rate limited for authentication, uploads and the assistant.

## Known limitations

- Rate limiting is per process, so counters reset on restart and aren't shared between instances. Behind a proxy, the IP comes from `X-Forwarded-For`, which a client can influence. The per-email login limit does not depend on it.
- There is no e-mail verification, password reset flow or multi-factor authentication.
- Files are not virus-scanned. They are validated as images and re-encoded for display, but originals are stored as uploaded.
- Files and the database are not encrypted by the application. Use encrypted storage at the hosting level.
- The application has had an internal review only, not an independent penetration test.
