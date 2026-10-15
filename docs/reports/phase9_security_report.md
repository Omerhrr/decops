# DecOps Security Test Report — Phase 9

**Scope**: DecOps API (FastAPI backend, `backend/app`) and authentication/authorization
surfaces. **Date**: 2026-10-15. **Environment**: sandbox development stack
(SQLite dev DB, Nuxt dev server proxying `/api`).

## 1. Method

- Automated hardening suite `backend/tests/test_hardening.py` (17 tests) executed
  against the application factory with an isolated per-test database.
- Targeted penetration probes (unauthenticated endpoint matrix, IDOR, privilege
  escalation, mass assignment) executed the same way a black-box pass would —
  through the public HTTP surface only.
- Code review of authentication, session, storage, and export paths
  (`app/services/auth_service.py`, `app/api/v1/auth.py`, `app/services/collaboration_service.py`,
  `app/services/report_service.py`, `app/services/import_service.py`).

## 2. Findings and status

| # | Area | Check | Result | Evidence |
|---|------|-------|--------|----------|
| 1 | Transport/session | Cookie flags `HttpOnly`, `SameSite=Lax`, `secure` follows deployment flag | PASS | `auth.py` set_cookie; test `TestSessionSecurity::test_login_cookie_flags` |
| 2 | Session | Forged session token rejected (opaque token, SHA-256 stored) | PASS | `test_forged_session_token_rejected` |
| 3 | Session | Logout revokes session immediately | PASS | `test_logout_revokes_immediately` (already covered in Phase 2 suite; re-verified) |
| 4 | Auth | Login non-enumeration (unknown user ≡ wrong password) | PASS | Phase 2 suite `test_auth.py` (re-verified in this pass) |
| 5 | Auth | Password material never in responses or audit metadata | PASS | `test_password_never_in_response_or_audit` |
| 6 | Headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP, `Cache-Control: no-store` on every response (success AND error) | PASS (new in Phase 9) | `SecurityHeadersMiddleware`; `TestSecurityHeaders` |
| 7 | Headers | HSTS only emitted for HTTPS deployments (`secure_cookies=True`) | PASS (new) | `test_hsts_only_for_https_deployments` |
| 8 | API surface | All 12 protected endpoint groups return 401 unauthenticated | PASS | `TestUnauthenticatedMatrix::test_every_protected_endpoint_requires_authentication` |
| 9 | API surface | Mutations (tasks/users/departments/exports) require authentication | PASS | `test_mutations_require_authentication` |
| 10 | API surface | OpenAPI docs disabled in production environment | PASS | `test_openapi_disabled_behind_production_flag` |
| 11 | Access control | Private task invisible to non-participants on detail/comments/attachments/activity (IDOR) | PASS | `test_private_task_hidden_from_everyone_else` |
| 12 | Access control | Task mutation by unauthorized user → 404 (non-enumerating) | PASS | same test |
| 13 | Access control | Department Member blocked from user administration and import center | PASS | `test_member_cannot_reach_administration` |
| 14 | Access control | System Administration holds no `imports.view`/`imports.manage` (spec restriction on technical administration) | PASS | Phase 8 suite `test_system_administrator_cannot_see_imports` (re-verified) |
| 15 | Input handling | Invalid UUID path parameters rejected cleanly (422/404, no stack traces) | PASS | `test_invalid_uuids_rejected_cleanly` |
| 16 | Input handling | Mass assignment ignored: identity fields (`task_number`, `created_by_id`) not settable through PATCH; AC-18 version cannot be attacker-supplied | PASS | `test_mass_assignment_cannot_change_identity_fields` |
| 17 | Input handling | Self-service profile update cannot grant roles/permissions | PASS | `test_profile_update_cannot_self_escalate` |
| 18 | Content safety | CSV export formula-injection sanitization (`=`, `+`, `-`, `@` prefixes) | PASS | Phase 7 suite `test_reports.py` (re-verified) |
| 19 | Content safety | Attachment downloads: storage key never exposed, path-traversal guarded, per-task authorization enforced | PASS | Phase 6 suite `test_collaboration.py` (re-verified) |
| 20 | Content safety | Imported attachment links stored verbatim as untrusted references, never fetched | PASS | Phase 8 suite `test_imports.py` |
| 21 | Audit | Every mutation in the coverage matrix produces an audit event with actor + timestamp | PASS | `TestAuditCoverageMatrix` |
| 22 | Throttling | Login throttling with lockout after repeated failures | PASS | Phase 2 suite `test_auth.py` (re-verified) |

## 3. Fixed during this phase

- **Security headers middleware added** (`app/main.py::SecurityHeadersMiddleware`):
  `nosniff`, `DENY` framing, `no-referrer`, restrictive CSP
  (`default-src 'none'; frame-ancestors 'none'`), and `Cache-Control: no-store`
  on all API responses; HSTS activates only behind the HTTPS deployment flag.
- **Explicit eager-loading of `assignments`/`access_grants`** in the register and
  dashboard authorization loops as defense-in-depth (see performance report —
  model-level `lazy="selectin"` already prevented N+1).

## 4. Known limitations (accepted for sandbox)

- SQLite in development is not a hardened datastore; production uses PostgreSQL
  with network-isolated credentials (runbook §2).
- No rate limiting on endpoints other than login throttling; recommended before
  public exposure (not required for the internal-only deployment target).
- The penetration pass is functional/API-level; an infrastructure/network
  penetration test is out of scope for the application team and is listed in the
  production runbook prerequisites.

## 5. Conclusion

All automated security checks pass (17 new hardening tests; 335 total suite).
No critical or high-severity issues remain open. The application is ready for
Interdec's production-approval review (UAT sign-off).
