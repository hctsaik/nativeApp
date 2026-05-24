# Tasks

- [x] Add a Management Center database behavior port.
- [x] Add a SQLite adapter for the existing platform schema.
- [x] Refactor Management Center insights to use the port.
- [x] Refactor Management Center UI helpers to use the port instead of SQL.
- [x] Refactor permission checks to use the port.
- [x] Refactor portal tool adapter reads/writes to consume the management store after schema initialization.
- [x] Delegate shared `PluginRegistry` publish/version/sheet/audit persistence operations to the port.
- [x] Add a Management Center use case layer for publish, rollback, Sheet Prod gating, Sheet CRUD auditing, tool Prod toggles, and integrity repairs.
- [x] Move `PluginRegistry` schema migration behind a dedicated SQLite schema service.
- [x] Fix rollback so an invalid version id cannot clear the active snapshot.
- [x] Add adapter unit tests for tool flags, ordering, audit, permissions, and dump behavior.
- [x] Add adapter contract-style tests for publish/version activation, Sheet lifecycle, and Prod module listing.
- [x] Add Oracle ManagementStore adapter with optional `oracledb` dependency and fake-connection tests.
- [x] Add use case regression tests for publish audit, rollback audit, Sheet Prod gate, Sheet CRUD audit, and integrity repair.
- [x] Add rollback regression coverage.
- [ ] Future: add Oracle schema/migration service and real Oracle integration tests.
- [ ] Future: define separate ports for module-owned annotation and manifest databases.
