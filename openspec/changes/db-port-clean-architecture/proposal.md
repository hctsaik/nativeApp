# Proposal: Database Port Clean Architecture

## Why

Management Center features now depend on platform persistence for tool
catalogs, publish snapshots, sheets, permissions, audit events, and integrity
checks. Those behaviors were previously spread across direct SQLite calls in
UI and application modules, making it hard to switch to Oracle or another
database without touching many callers.

## What Changes

- Introduce a Management Center persistence port that defines database behavior
  in application terms.
- Add a SQLite adapter implementing that port for the existing `tools.sqlite`
  schema.
- Move Management Center read/write flows away from direct `sqlite3` and SQL.
- Keep `PluginRegistry` as the public application service while delegating
  shared persistence behaviors to the port.
- Add use cases that centralize publish, rollback, Sheet Prod gating, Sheet
  CRUD auditing, tool Prod toggles, and integrity repairs.
- Add contract-style adapter tests so another database adapter can prove the
  same behavior.
- Add an Oracle management-store adapter with named binds and Oracle
  `RETURNING ... INTO` handling.
- Document the bounded-context split between platform persistence and
  module-owned databases.

## Impact

- SQLite remains the default implementation.
- Management Center, auth permission checks, and insight functions can be
  tested through a stable behavior interface.
- Future Oracle support can implement the same port without changing
  Management Center UI or insight code.
