# CodeGate

**AI-Powered Pull Request Quality Intelligence Platform**

CodeGate is a comprehensive Pull Request Quality Intelligence Platform that analyzes Pull Requests using AI-assisted review, static analysis, test evidence, and changed-code coverage. It provides explainable Quality and Risk Scores, Merge Policy evaluation, reviewer recommendations, and an engineering analytics dashboard.

*If you are reviewing this project for a defense or presentation, please start here: [**Final Defense & Documentation Index**](docs/README.md).*

**Vietnamese technical handbook and repair notes:** [Architecture, setup, verified fixes, and limitations](docs/CODEGATE_TECHNICAL_HANDBOOK_VI.md).

**Try the interactive dashboard:** [Public demo](https://codegate-demo.vercel.app) ·
[Real local runtime video · Vietnamese narration](https://codegate-demo.vercel.app/recordings/codegate-runtime-vi.mp4).
The public dashboard uses clearly labelled sample data and browser-local edits. The separate video records real
Git revisions, Ruff/Bandit/Radon, pytest/coverage, PostgreSQL and the existing scoring/policy services on a controlled
local fixture. GitHub OAuth/App, AI review and GitHub publishing are not exercised in that recording.
See [demo deployment](docs/PUBLIC_DEMO.md) and [runtime scope and limitations](docs/RUNTIME_RECORDING.md).

## What CodeGate Does

When a developer opens or updates a Pull Request:
1. **GitHub PR** triggers an event.
2. **GitHub Webhook** is received by CodeGate.
3. **Async Analysis** is enqueued and processed by Celery Workers.
4. **AI Review** evaluates the code changes for bugs, security, and quality issues.
5. **Static Analysis** scans the AST for deterministic flaws.
6. **Tests/Coverage** are evaluated when explicitly configured; execution is disabled by default.
7. **Quality Score & Risk Score** are computed based on findings.
8. **Policy** is evaluated (PASS, WARNING, BLOCK).
9. **Reviewer Recommendation** suggests the best engineers to review the PR.
10. **GitHub Check** is published back to the PR with the results.
11. **Dashboard** visualizes the data and provides engineering analytics.

## Core Features

- **Automated Code Review:** Deterministic static analysis combined with probabilistic AI insights.
- **Quality & Risk Scoring:** Explainable scores mapped to your team's quality gates.
- **Merge Policy Engine:** Blocks, warns, or passes based on strict, configurable evidence.
- **Reviewer Recommendations:** Smart suggestions based on CODEOWNERS, file history, and directory expertise.
- **Full Analytics Dashboard:** React/Vite SPA for exploring PR quality trends and tenant data.
- **Configurable Test Execution:** Docker-based execution with resource limits and workspace validation; a dedicated worker and deployment validation are required for untrusted code. Local execution requires explicit operator opt-in and trusted repositories.

## Architecture

```mermaid
flowchart TD
    User([Developer]) -->|Opens PR| GH[GitHub]
    GH -->|Webhook Event| API[FastAPI Webhook Handler]
    API -->|Enqueue AnalysisJob| DB[(PostgreSQL 16)]
    API -->|Job Data| Redis[(Redis Broker)]
    Redis --> Worker[Celery Worker]
    Worker --> AI[AI Reviewer\nGroq/LiteLLM]
    Worker --> SA[Static Analysis\nRuff/Bandit]
    Worker --> TE[Test Executor\nDocker]
    AI --> Scoring[Scoring Engines\nQuality, Risk, Policy]
    SA --> Scoring
    TE --> Scoring
    Scoring --> DB
    Scoring --> GHCheck[GitHub Check API]
    GHCheck --> GH
    DB --> Web[React Dashboard]
```

## Technology Stack

- **Backend:** FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL 16
- **Queue:** Redis + Celery
- **Frontend:** React + Vite
- **Runtime:** Docker Compose
- **AI:** PR-Agent foundation + LiteLLM-compatible provider configuration (e.g., Groq)
- **Static Analysis:** Ruff, Bandit, Radon
- **Testing:** DockerTestExecutor

## Requirements

### Normal User Requirements
- Windows 10/11, macOS, or Linux
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (must be running)
- Internet connection (for GitHub and external AI provider access)
- A GitHub account and repository access

*Note: You do not need Python or Node.js installed to run the packaged product.*

### Developer Requirements
- Python 3.12+
- Node.js 20+
- Git
- Docker Engine / Docker Desktop

## Documentation Quick Links

- [**First Time Setup (Clone & Run Guide)**](docs/FIRST_RUN.md)
- [**Environment Configuration Guide**](docs/CONFIGURATION.md)
- [**Architecture Deep Dive**](docs/ARCHITECTURE.md)
- [**GitHub App Setup**](docs/GITHUB_APP_SETUP.md)
- [**AI Configuration**](docs/AI_CONFIGURATION.md)
- [**Troubleshooting**](docs/TROUBLESHOOTING.md)

## 🤝 Upstream Attribution

CodeGate extends the open-source **PR-Agent** framework.
- **PR-Agent provided**: Foundational LLM wrappers (LiteLLM) and GitHub connection scaffolding.
- **CodeGate implemented**: The persistent PostgreSQL database layer, Static Analysis orchestrators, Quality/Risk scoring, Policy Engine, Reviewer Recommendation, Test execution, React Dashboard, and CI/CD security pipelines.
- CodeGate does not claim authorship over original PR-Agent code.

## 📜 License

MIT License. Upstream copyrights belong to their respective owners. CodeGate-specific additions are licensed under the same terms.
