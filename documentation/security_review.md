# PureFlow Security Review

**Review date:** 2026-11-14  
**Scope:** repository configuration and code paths exercised in the Phase 9 audit. This is a code-level review, not a penetration test.

## Controls observed

- Flask debug mode is disabled by default and enabled through `PUREFLOW_DEBUG`; `PUREFLOW_HOST`, `PUREFLOW_PORT`, and `PUREFLOW_CORS_ORIGINS` configure the development server and CORS allowlist. Existing `AQUAINTEL_*` environment variables remain supported as fallbacks for current deployments.
- CORS excludes wildcard configuration and defaults to local Vite origins. The E2E test confirms an unexpected origin receives no CORS allow header.
- Upload handlers use Werkzeug filename sanitisation and supported-format checks. The request cap is configured at 101 MiB to accommodate multipart overhead for a 100 MiB file. Error cases and a traversal-style filename were exercised in the temporary test workspace.
- SQLite connections enable foreign keys. Custom SQL is opened read-only, restricted to one SELECT/CTE statement via an authorizer, parameterized for values, and limited to at most 500 returned rows. Tests reject DELETE, DROP, mutating CTE, and multi-statement attempts.
- Report download uses a constrained report ID/format lookup and only serves generated report paths. Export formats are allowlisted.
- Database reload requires explicit confirmation. The loader rollback behavior is covered by a temporary database test.
- Generic SQLite errors are mapped at app level to a generic 503 message; logs retain diagnostic context.

## Risks and actions

| Finding | Risk | Recommended action |
|---|---|---|
| No authentication or authorization | Anyone who can reach the API may upload, process, query, or generate reports; CORS does not provide access control. | Add an authenticated deployment boundary and authorization for data-changing operations before exposing beyond a trusted local network. |
| Deletion leaves derived/loaded data | Removing a source from the dataset index does not cascade to curated/transformed files, quality reports, or SQLite records. | Define retention semantics and implement a coordinated, audited deletion workflow with clear confirmation and transactional cleanup strategy. |
| Large file parsing is memory-bound | A valid request near the configured cap may exhaust worker memory depending on shape and parser overhead. | Add resource limits and representative memory/load tests; consider streaming/chunked parsing where feasible. |
| CORS origin configuration is deployment-sensitive | Incorrectly configured origins may expose browser-readable API responses to an unintended site; CORS is not authentication. | Set explicit production origins and keep the service behind authentication/network controls. |
| No automated browser security or dependency audit in this pass | Frontend behavior, CSP/security headers, and dependency advisories were not comprehensively assessed. | Add deployment headers and a scheduled dependency/security scanning workflow. |

## Configuration and test boundaries

No `.env` file was identified in the workspace scan. Frontend configuration uses `VITE_API_BASE_URL`; backend CORS, debug, host, and port are environment-configurable. No production secret-management workflow was assessed. Destructive checks were limited to temporary workspaces; the actual source CSV and checked-in SQLite data were not deleted or rewritten by the E2E test.

## Review conclusion

The repository has useful local safeguards for upload paths, SQL query mode, report export selection, database integrity, and development defaults. It is not ready for untrusted multi-user exposure without authentication/authorization, explicit lifecycle handling for derived data, deployment hardening, and resource testing.
