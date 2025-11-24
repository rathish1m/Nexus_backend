# Nexus Backend – Technical Audit Report
Addressed to the repository owner

## Overview
We analysed the Nexus Telecoms Django backend with a focus on security posture, operational readiness, and test discipline. The codebase demonstrates substantial feature depth, but several high‑impact risks require immediate attention. Key issues include unauthenticated payment callbacks, lax password-reset handling, insecure production defaults, orphaned Celery scheduling, schema drift, and shallow automated testing.

## Critical Findings
- 🚨Unauthenticated payment webhook (Critical)
flexpay_callback_mobile trusts any POST body, skips CSRF, and performs order fulfilment, wallet credits, and coupon redemption without signature or IP validation. A forged request needs only an order reference to mark invoices paid.
Evidence: api/views.py (lines 213-358)
Action: Enforce HMAC/shared-secret verification, reject unsigned payloads, and add idempotency and fraud monitoring before touching financial state.
- 🚨Password reset endpoint exposed (High)
The reset view is CSRF‑exempt and unauthenticated, with no throttling; it sends emails and leaks account existence via differing behaviour. Attackers can trigger resets or mount enumeration/brute-force attacks.
Evidence: user/views.py (lines 23-51)
Action: Reinstate CSRF (or use signed, time‑limited tokens), add rate limiting/recaptcha, and return identical responses regardless of account presence.

## High Severity Findings
- ⚠️Insecure defaults & embedded secrets
Production defaults fall back to DEBUG=True, Celery disables broker SSL verification, and a live Sentry DSN is committed. This weakens security and leaks telemetry.
Evidence: nexus_backend/settings.py (line 82), nexus_backend/settings.py (lines 438-444), nexus_backend/settings.py (lines 512-517)
Action: Default to DEBUG=False, require proper TLS with CA validation for Valkey/Redis, and move DSNs and credentials into env-secured config.
Major Issues
Broken Celery Beat schedule
The beat schedule targets subscriptions.generate_renewal_orders_daily, but no task with that name is registered, so beat will emit “unknown task” and skip renewals.
Evidence: nexus_backend/celery.py (lines 34-40), absence in codebase
Action: Restore the missing task or repoint the schedule to an existing billing task (e.g. run_prebill_and_collect).

- ⚠️Migration fails due to schema drift
main.0003 re-adds activation_requested, yet the column already exists in the database, causing DuplicateColumn on migrate.
Evidence: main/migrations/0003_installationactivity_activation_requested_and_more.py (lines 7-15)
Action: Inspect schema vs. migrations, adjust with conditional RunSQL, fake the migration, or rename the field so migrations reclaim authority.

## Medium Concerns
- Testing gaps vs. coverage claims
Tests cover only a handful of models/views and miss billing, webhook, and background task logic, yet README advertises 95 % coverage.
Evidence: tests/test_models.py (lines 5-63), tests/test_views.py (lines 5-87)
Action: Expand security/regression tests (webhook validation, billing totals, Celery jobs) and publish honest coverage metrics.

## Additional Observations
- Internal helper duplication (multiple _qmoney definitions) suggests maintenance creep; centralise shared utilities to reduce divergence.
- Numerous @csrf_exempt annotations in api/views.py increase attack surface; keep exemptions to the absolute minimum and wrap them with signature checks and rate limiting.
- README and Makefile advertise Docker and Celery workflows, but there’s no documented strategy for rotating secrets or configuring TLS for external services—document these steps to avoid insecure deployments.

## Recommended Actions
1. Lock down external entry points (FlexPay callbacks, password reset) with proper authentication, CSRF protection, and rate limiting.
2. Enforce secure defaults in configuration: DEBUG=False, broker TLS verification, secrets from environment.
3. Repair operational gaps by reconciling migrations, fixing Celery Beat tasks, and hardening logging/error handling.
4. Invest in automated testing around high-risk workflows (payments, billing renewals, Celery tasks) and update coverage reporting to reflect reality.
5. Document secure deployment practices—environment variables, TLS certificates, secret rotation—for ops teams.

## Open Questions
- What signature or IP validation does FlexPay support, and can it be adopted without contract changes?
- Should the password reset flow remain form-based (with CSRF protection) or move to an authenticated API with signed tokens? What rate-limiting infrastructure (Valkey/Redis, WAF) is available?
