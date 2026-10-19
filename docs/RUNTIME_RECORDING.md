# Recording a real local runtime

The opt-in harness in `tools/recording/` launches the existing CodeGate FastAPI app and adds local recording controls.
The dashboard continues to use its existing authenticated API routes and database services.
The harness does not import the old demo seeding script or fabricate findings, scores, test results or policies.

## Scope and prerequisites

Use the repository's Python 3.12+ virtual environment with its existing dependencies installed. No extra package is
required. Git, Ruff, Bandit, Radon, pytest, coverage, FastAPI and Uvicorn must be available in that environment.
All three static analyzers must be enabled. The CLI binds only to `127.0.0.1` and does not accept a host override.

Provide a dedicated local database URL in an explicit environment file, for example the recording infrastructure's
`../recording-infra/runtime.env`. The environment file must remain untracked. Without one, the harness creates an
isolated SQLite database at `.runtime/recording/recording.db`. It creates missing tables; it never drops existing tables.
Use a new database for a clean recording. Existing data is preserved.

```powershell
$env:PYTHONPATH = '.'
.venv/Scripts/python.exe -m tools.recording.server --env-file ../recording-infra/runtime.env --port 8000
```

Run the existing dashboard development server on `http://127.0.0.1:5173`. Its API client calls the backend directly
at port 8000 with credentials; this Vite configuration does not define an API proxy.
Use the same `127.0.0.1` hostname in both browser tabs so the host cookie is sent to the backend.
Set `CODEGATE_FRONTEND_URL` in the explicit environment file if using another dashboard URL.

## Record the execution

1. Open `http://127.0.0.1:8000/recording`.
2. Select **Open local session**. This inserts a real, expiring `AuthSession` record and sets the standard HttpOnly
   `codegate_session` cookie. The user provider is `local-recording`; this is explicitly not a GitHub OAuth login.
3. Select **Analyze regression**. The control waits for actual analyzer and test subprocesses to finish.
4. Open the existing CodeGate dashboard and inspect the persisted local source run, its findings and tests.
5. Return to the control tab and select **Analyze fix**, then refresh the existing dashboard to inspect the next run.

Each server session generates a trusted local Git fixture with three real commits: baseline, deliberately regressed source,
and corrected source. Both cases use the same source repository and baseline SHA. The regression changes addition into subtraction, includes an unused import and introduces an
unexecuted `eval` function. Ruff and Bandit identify the actual source issues; two actual pytest cases fail. The fixed
revision removes the unsafe function/import and restores addition, so both pytest cases pass.

The fixture source and SHA values are retained under `.runtime/recording/fixture-*`. The existing `StaticAnalysisRunner`
fetches the selected SHA into its normal temporary checkout and invokes the real Ruff, Bandit and Radon commands.
The harness requires three actual persisted successful analyzer runs before running tests or calculating scores.
Disabled static analysis, a missing analyzer or a failed analyzer makes the analysis fail instead of completing it.
The existing `PytestRunner` uses `LocalTrustedExecutor` with an explicit workspace root restricted to the generated
fixture. It runs real pytest and coverage subprocesses. No arbitrary repository URL or command is accepted by the
recording endpoints. This executor is for this trusted generated source; it is not a sandbox for untrusted pull requests.

Test and coverage outputs are parsed and persisted through `TestingStore`. `ChangedLinesResolver` computes the actual
Git diff and intersects executable changed lines with coverage. The normal quality, risk and policy services calculate
and persist their outputs. The recording repository's policy enables required tests and changed coverage gates.

## Expected honest results

The regressed revision has failed tests and a **BLOCK** policy decision. The fixed revision has passed tests, 100%
coverage of its executable changed line and a **WARNING** policy decision. The production policy intentionally warns
when quality dimensions are incomplete. Maintainability is unavailable in this configuration. The current production
quality engine assigns its `ai_review` subscore from the absence of AI findings, so it can display 100 even though
`ai_model` is null and no AI request ran. That subscore is not evidence of a successful AI review. The harness preserves
the existing engine behavior and reported missing dimensions; it does not alter scoring to obtain a full PASS.

GitHub OAuth, GitHub App, AI review and GitHub check publication are **not configured or exercised**. The harness
does not run the full GitHub PR ingestion pipeline. Analysis is awaited by the local HTTP request and does not use
Celery; a running Redis container is not evidence of queue execution. PostgreSQL is used when its URL is supplied,
and the status response identifies the actual SQLAlchemy database dialect.

## API and evidence

- `POST /api/v1/recording/session`: create the local session cookie.
- `POST /api/v1/recording/analyze` with JSON `{"case":"unsafe"}` or `{"case":"safe"}`: await actual execution.
- `GET /api/v1/recording/status`: database dialect, running state, integration availability and the latest ten real runs.

The analysis response includes database IDs, base/head SHAs, raw persisted analyzer findings and metrics, parsed test
and coverage results, quality/risk breakdowns and policy rule explanations. An identical evidence snapshot is written
to `.runtime/recording/evidence/analysis-<id>.json`. These ignored local artifacts contain no provider tokens.
Control endpoints reject non-loopback clients, non-local Host headers and malformed or non-local browser origins.
Do not reverse-proxy them to the public
internet or package this harness as the production authentication mechanism.

## Verification

```powershell
$env:PYTHONPATH = '.'
.venv/Scripts/python.exe -m pytest tests/codegate/test_recording_harness.py -q
.venv/Scripts/python.exe -m ruff check tools/recording tests/codegate/test_recording_harness.py
.venv/Scripts/python.exe -m flake8 tools/recording tests/codegate/test_recording_harness.py --max-line-length 120
```

The integration test creates an isolated SQLite database and real local repositories, invokes the same subprocesses,
and checks both outcomes, persisted records, coverage and absence of AI findings. The authentication test verifies
that the local session stores only the SHA-256 token hash in the existing session table.
