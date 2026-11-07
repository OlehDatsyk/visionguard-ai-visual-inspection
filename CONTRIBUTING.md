# Contributing

## Getting started

1. Fork the repository and clone your fork.
2. Create a branch from `main`, for example `git checkout -b fix/upload-error-message`.
3. Set up the project.

Backend, from `backend/`, with a virtual environment active:

```bash
pip install -r requirements-dev.txt
```

```bash
python scripts/download_models.py
```

Frontend, from `frontend/`:

```bash
npm ci
```

See [INSTRUCTION.md](INSTRUCTION.md) for details.

## Coding standards

- **Python:** type hints, and small functions. Routes stay thin, business logic goes in `services/`, and `vision/` knows nothing about HTTP or the database.
- **TypeScript:** strict mode. All API calls go through `services/api.ts`. No `any` without a reason.
- **Permissions:** every route that touches user data must use the `owned_*` helpers in `api/deps.py`.
- **Database:** change models with an Alembic migration:

```bash
python -m alembic revision --autogenerate -m "describe the change"
```

- **Honesty rules, which are not optional:**
  - Never present an uncertain result as a confirmed defect.
  - Never add a capability claim, accuracy figure or confidence description you haven't measured.
  - Never add fabricated results outside clearly labelled demo data.
  - Heuristic findings stay capped below "high" confidence.
  - Never commit secrets, private images, databases, reports or model weights.

## Testing requirements

All of these must pass:

```bash
cd backend && python -m pytest
```

```bash
cd frontend && npm run typecheck && npm test
```

- New behaviour needs tests. Security-sensitive changes need a test for the failure case too.
- Tests must not need network access. Use `FakeDetector` from `tests/conftest.py`. Real-model tests skip themselves when weights are absent.
- For interface changes, run the browser test as well: see [TESTING.md](TESTING.md).
- If you change routes, regenerate the API reference with `python scripts/generate_api_docs.py`.

## Pull requests

- Keep each one focused on a single change, and explain what changed and why.
- Include screenshots for interface changes.
- Say which tests you ran, and report honestly anything you could not test.
- Add an entry to [CHANGELOG.md](CHANGELOG.md).
- Check `git diff` for anything private before you push.
