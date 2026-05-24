# Design: Database Port Clean Architecture

## Scope

This change targets the platform management database first:

- `tools`
- `tool_versions`
- `sheets`
- `sheet_tabs`
- `plugin_permissions`
- `audit_events`
- roles used by Management Center display

Module-owned databases, such as annotation or manifest databases, remain their
own bounded contexts. They should receive separate ports once their domain
contracts are explicit.

## Architecture

Application and UI code depend on `ManagementStore`, a behavior port expressed
in platform terms:

- tool readiness records
- sheet reference records
- active snapshot content
- tool visibility and Prod flags
- version integrity repairs
- audit event recording and listing
- permission lookup
- backup/dump data for the System page

`SQLiteManagementStore` is the infrastructure adapter. It owns SQLite-specific
connection behavior, row conversion, SQL syntax, placeholders, and table dump
queries.

`OracleManagementStore` is the Oracle infrastructure adapter. It is optional at
import time and can be built with an explicit connection factory for tests or
with `oracledb` connection settings in production. It owns Oracle-specific
named binds, `MERGE` upserts, `RETURNING ... INTO` id retrieval, CLOB/Lob
reading, and `FETCH FIRST` pagination.

## Boundaries

- `management_insights.py` is application-level read logic. It consumes the
  port and returns typed readiness/preflight/diff data.
- `management_use_cases.py` is application-level write orchestration. It
  centralizes publish, rollback, tool Prod toggles, Sheet Prod gating, Sheet
  CRUD audit, and integrity repairs.
- `management_schema.py` owns SQLite schema creation, seed data, and legacy
  migration compatibility for the platform management database.
- `tools/management_runner.py` is UI. It calls application services and the
  port, not SQL.
- `auth_provider.py` uses the permission behavior rather than reading SQLite
  directly.
- `plugin_registry.py` remains the public lifecycle service. Its filesystem
  scanning stays there, while publish/version/sheet/audit persistence
  operations move behind the port.

## Oracle Readiness

The port avoids exposing SQLite rows or connections to callers. A future Oracle
adapter should map:

- placeholder syntax
- transaction boundaries
- autoincrement/identity columns
- timestamp defaults
- JSON serialization and CLOB handling
- table dump/backup behavior

The implemented Oracle adapter covers the ManagementStore behavior surface, but
runtime cutover still requires an Oracle schema/migration service and deployment
configuration for Oracle credentials/DSN. Until that exists, production runtime
continues to instantiate the SQLite schema/store by default.

The application layer should not import `sqlite3`, issue SQL, or depend on
SQLite `Row` objects.

## Migration Strategy

This is an incremental refactor. The implemented slice removes direct SQL from
Management Center UI, auth, and insights, moves publish/version/sheet/audit
write behavior into the store, adds use case tests around critical write
workflows, and moves SQLite schema ownership into `SQLiteManagementSchema`.

## Testing Strategy

The SQLite adapter is covered by contract-style tests that verify behavior
rather than SQL text:

- publish and activate versions
- invalid version activation preserves the current active snapshot
- Sheet lifecycle and Prod listing
- tool flags, ordering, permissions, audit, and table dump behavior
- Oracle named bind and `RETURNING ... INTO` behavior with fake connections

Use case tests verify Management Center workflows:

- publish writes a snapshot and audit payload
- rollback changes the active version and audits the action
- Sheet Prod enable blocks unready references
- Sheet CRUD and Dev toggles audit changes
- integrity repair normalizes active versions and records repair metadata
