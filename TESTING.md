# Testing

Results below were recorded on 2026-11-07. They come from real runs, and anything not run is listed as such.

## Test environment

| Item | Version |
|---|---|
| Operating system | Windows 11 Home |
| Python | 3.12.10 |
| Node.js and npm | 24.20.0 and 11.19.0 |
| PostgreSQL | 16.2, from the `pgserver` package, used for testing only |
| Browser | Microsoft Edge 156, headless |
| Model | YOLOX-Tiny, real weights |

## Commands

Backend, from `backend/`, with `requirements-dev.txt` installed:

```bash
python -m pytest
```

```bash
python -m pytest --cov=app
```

On PostgreSQL. **This drops all tables in the target database**, so point it at a throwaway one:

```bash
TEST_DATABASE_URL=postgresql://user:password@localhost:5432/visionguard_test python -m pytest
```

Frontend, from `frontend/`:

```bash
npm run typecheck
```

```bash
npm test
```

Browser test, with the app running, Edge or Chrome installed, and a throwaway database:

```bash
python ../backend/scripts/make_e2e_fixtures.py e2e/fixtures
```

```bash
APP_URL=http://127.0.0.1:5173 E2E_OUTPUT=e2e/output E2E_SHOTS=e2e/output/shots npm run e2e
```

Use `E2E_BROWSER=chrome` for Chrome. Without `E2E_SHOTS`, the test overwrites `docs/screenshots`.

## Results

| Suite | Result |
|---|---|
| Backend tests on SQLite | **112 passed** (version 1.0.1, including 6 tests for single-service mode and blank variables) |
| Backend tests on PostgreSQL 16 | **106 passed** (version 1.0.0, not rerun for 1.0.1) |
| Backend line coverage | **93%** across `app/` |
| Frontend unit and component tests | **14 passed** |
| TypeScript strict type check | No errors |
| Browser test, launcher-started app from a clean copy (development mode, SQLite) | **36 checks passed** |
| Browser test, Render's start and build commands (production mode, PostgreSQL) | **36 checks passed** |
| Browser test, single-service mode: the container start script with the API serving a `VITE_API_BASE_URL=/` build (production mode, SQLite, no `SECRET_KEY`) | **36 checks passed**, with the page's Content-Security-Policy enforced |
| `alembic upgrade`, `check`, `downgrade`, `upgrade` on SQLite and PostgreSQL | Passed, with no drift from the models |
| `pip-audit` on runtime requirements | No known vulnerabilities |
| `npm audit` | 0 vulnerabilities |

### What the suites cover

| Area | Tests include |
|---|---|
| **Authentication** | Registration, login, hashing, forged and revoked tokens, rate limiting, identical failure responses |
| **Permissions** | A second user gets 404 on another user's projects, images, files, findings, comparisons, reports and conversations |
| **Image upload** | All formats, per-file accept or reject, EXIF stripping, the original kept byte-identical |
| **Invalid files** | Scripts disguised as images, wrong extensions, GIF, SVG, truncated, empty, oversized, decompression bomb, animated, traversal names |
| **Vision** | Controlled images with known marks, located by position; clean surfaces produce no defects; complex scenes skip heuristics; real YOLOX finds a cat and a cup |
| **Comparison** | Identical images, camera shift recovered with a real change located, lighting change warned about, unrelated images warned about |
| **Jobs** | Lifecycle, automatic retry, safe failure messages, manual retry, crash recovery |
| **Reports** | Required sections present, no server paths or secrets in the text, demo label |
| **Analytics** | Empty states, figures matching records, no false-positive rate without decisions |
| **Assistant** | Answers from records, no invention on empty records, provider fallback, usage limit |
| **Errors** | Internal exceptions never reach responses, and validation errors don't echo passwords |
| **Browser** | The whole workflow, every sidebar page, deep-link refresh, no sideways scrolling at phone width on nine pages, no console errors |

## Problems found and fixed during testing

- Long truncated text widened the page at phone width (found by the browser test).
- Large findings created a false "surface anomaly" halo around themselves (found by reviewing screenshots).
- A PDF test helper failed intermittently because it stripped a valid trailing character (found by the clean environment run).
- The default port 8000 clashed with another local app, so the default is now 8010, and the launcher reports busy ports.
- Windows line endings would have broken the macOS launcher, so `.gitattributes` now fixes line endings.

## Measured resources

| Measure | Result |
|---|---|
| Per-image analysis on a 16-thread desktop | About 0.2 to 0.9 seconds |
| Backend memory after the browser test | About 320 MB |
| Peak backend memory, `ONNX_THREADS=1` | 401 MB |
| Peak backend memory, `ONNX_THREADS=2` | 403 to 445 MB |

## Not tested

| Item | Why, and what was done instead |
|---|---|
| **Live Render deployment** | Not deployed. `render.yaml` was checked against Render's documentation and parsed as YAML, but Render has not validated it. Its commands ran locally |
| **HTTPS and the static site's Content-Security-Policy** | They only apply on the live site. Test these first after deploying |
| **macOS, including `Start App.command`** | No Mac was available. Its syntax was checked with `bash -n`, and the shared launcher was tested on Windows |
| **Docker, the root `Dockerfile` and `docker-compose.yml`** | Docker was not installed. The root image's start script and app were run locally on Windows instead |
| **Live Anthropic API** | No key was used. The provider is tested against a mocked client, including errors and refusals |
| **Real S3 storage** | The adapter is tested against a stubbed client only |
| **Separate `python -m app.worker` process** | Only the in-process worker was exercised. The same job code runs in both |
| **PDF display in the browser preview** | The preview's iframe loads in the headless browser, but its rendered look was not checked. A downloaded report was rendered to an image and reviewed |
| **Detection accuracy on real defects** | No labelled dataset exists. The defect heuristics were only tested on generated images with known marks |
| **Load and concurrency** | No load testing was done |
| **Independent security review** | Only an internal review |

## Known issues

- The Windows path limit stops OpenCV from loading, and Git from adding files, in very long folders. The launcher detects a long path and explains how to fix it.
- Rate limits are per process.

## Manual verification steps

1. Start the app, register, and choose **Explore demo data**.
2. In **Object recognition sample**, confirm that boxes appear on the coffee cup and the cat.
3. In **Surface condition survey**, select a finding, zoom in, and record a decision.
4. In **Image Comparison**, open the demo, then try the slider and the difference view.
5. Generate a report and read it.
6. On **Model Information**, confirm that availability matches reality. Rename `backend/model_weights`, restart, and confirm that it says unavailable. Rename it back.
7. Upload a renamed text file, and confirm that it is rejected with a reason.
8. Open the app in a private window, register as a second user, and confirm that the first user's records aren't visible.
