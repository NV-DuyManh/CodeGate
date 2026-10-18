# CodeGate Documentation Index

- [**Vietnamese Technical Handbook**](CODEGATE_TECHNICAL_HANDBOOK_VI.md): Architecture, source map, scoring, setup, verified repairs, demo guide, and remaining limitations (18 October 2026).

Welcome to the CodeGate developer and architecture documentation. CodeGate is a complex platform combining AI inference, static analysis, containerized testing, and a web dashboard. 

This directory contains the final, authoritative documentation for understanding, configuring, and extending the platform.

## 1. Getting Started
- [**First Run & Clone Guide**](FIRST_RUN.md): Step-by-step instructions for getting the platform running from a fresh clone.
- [**Handover Checklist**](HANDOVER_CHECKLIST.md): A quick checklist for new developers to verify their setup.

## 2. Configuration & Integrations
- [**Environment Configuration**](CONFIGURATION.md): Detailed breakdown of every required and optional environment variable.
- [**GitHub App Setup**](GITHUB_APP_SETUP.md): Instructions for creating the GitHub App required for PR webhooks.
- [**AI Configuration**](AI_CONFIGURATION.md): Configuring LiteLLM and providers like Groq or OpenAI.
- [**Authentication**](AUTHENTICATION.md): How GitHub OAuth is used for user session management.

## 3. Architecture & Internal Systems
- [**Architecture Overview**](ARCHITECTURE.md): The high-level system design and component interaction.
- [**Database**](DATABASE.md): PostgreSQL 16 schema and Alembic migration system.
- [**Async Pipeline**](ASYNC_PIPELINE.md): How Celery and Redis orchestrate background analysis jobs.
- [**RBAC**](RBAC.md): Role-Based Access Control matrix and tenant isolation boundaries.
- [**Security**](SECURITY.md): Secrets management, test boundaries, and webhook signatures.

## 4. Scoring Engines
CodeGate uses deterministic and probabilistic engines to evaluate code:
- [**Quality Score Mechanics**](QUALITY_SCORE.md): How the 0-100 Quality Score is calculated.
- [**Risk Score Mechanics**](RISK_SCORE.md): How the Critical/High/Medium/Low Risk Level is calculated.

## 5. Operations
- [**Troubleshooting**](TROUBLESHOOTING.md): Solutions for common local setup and runtime issues.
- [**archive/**](archive/): Historical implementation reports, audits, and design documents from the development phases.
