# Phase 5 — Orchestration Job API Spec

## Objective

Replace the two job stubs in `handlers.py` (lines 227–231) with a real job engine.
Introduce `AuditLog`, dead-letter handling, and proper job state machine. Disambiguate
`task_id` (= `annotation_set_id` alias) from the new `job_id` namespace.

## Requires

Phase 4 complete (jobs table must exist in DB; `tenant_id` on all tables).

## Critical Naming Fix (must ship before Phase 5)

Current: `get_task(task_id)` at `services.py` line 107 uses `task_id` as an alias for
`annotation_set_id`. Phase 5 introduces real jobs with their own `job_id`.

Resolution: keep `get_task()` / `list_tasks()` as they are (they return annotation sets).
New job methods use `job_id` exclusively. Document the alias relationship explicitly in
`services.py` docstring. Do not rename existing methods — MCP tool `annotation_get_task`
must remain callable.

## Files to Modify

```
mcp/annotation_mcp/handlers.py         — replace stubs; add new job tools
annotation/services.py                 — add job service methods
annotation/storage/sqlite_store.py     — add job and audit_log CRUD
```

## Job State Machine

```
queued ──► running ──► succeeded
                  └──► failed ──► (retry_count < max) ──► queued
                             └──► (retry_count >= max) ──► dead_letter
                  └──► partial ──► running  (resume)
```

States stored as TEXT in `jobs.state`. Transitions written as AuditLog entries.

## New Service Methods (`services.py`)

```python
def create_import_job(
    self,
    profile_id: str,
    query: dict,
    options: dict | None = None,
    tenant_id: str = "",
) -> dict:
    """Create and enqueue an import job. Returns {job_id, state}."""

def create_export_job(
    self,
    annotation_set_id: str,
    export_format: str,
    options: dict | None = None,
    destination_profile_id: str | None = None,
    tenant_id: str = "",
) -> dict:

def dry_run_export_job(
    self,
    annotation_set_id: str,
    export_format: str,
    destination_profile_id: str | None = None,
    tenant_id: str = "",
) -> dict:
    """Synchronous. Returns ConversionReport dict immediately (no job_id)."""

def get_job_status(self, job_id: str, tenant_id: str = "") -> dict:
    """Replaces stub. Reads real jobs table."""

def cancel_job(self, job_id: str, tenant_id: str = "") -> dict:
    """Replaces stub. Transitions running→failed with cancel reason."""

def get_conversion_report(self, job_id: str, tenant_id: str = "") -> dict:
    """Returns ConversionReport stored in jobs.payload after export."""

def list_dead_letter_jobs(self, tenant_id: str = "") -> list[dict]:

def retry_dead_letter_job(self, job_id: str, tenant_id: str = "") -> dict:
```

## Job Runner

Phase 5 MVP: synchronous job runner (jobs run in-process when `get_job_status` is
polled or via direct call). Background async execution deferred to Phase 5+.

For MVP:
- `create_import_job` enqueues the job (state=queued) and immediately starts execution
- Caller polls `get_job_status(job_id)` — by MVP time, job is already done
- This is consistent with current behaviour ("MVP operations run synchronously")

## AuditLog (`sqlite_store.py` additions)

```python
def write_audit_log(
    self,
    job_id: str | None,
    actor: str,
    action: str,
    payload: dict,
    tenant_id: str = "",
) -> None:
    """Append-only. No UPDATE or DELETE on audit_log table ever permitted."""

def list_audit_log(self, job_id: str, tenant_id: str = "") -> list[dict]: ...
```

## Dead-letter Handling

Job transitions to `dead_letter` when `retry_count >= max_retries` (default: 3).
AuditLog entry written with full error traceback in payload.

New MCP tools:
- `annotation_list_dead_letter_jobs(tenant_id?)` → list of job dicts
- `annotation_retry_job(job_id)` → {job_id, state}

## MCP Tool Changes (`handlers.py`)

### Replace stubs (lines 227–231)

```python
# Before (always returns succeeded):
def get_job_status(self, job_id): return ok({"state": "succeeded", ...})
def cancel_job(self, job_id): return ok({"state": "not_cancelable", ...})

# After:
def get_job_status(self, job_id): return ok(self.service.get_job_status(job_id))
def cancel_job(self, job_id): return ok(self.service.cancel_job(job_id))
```

### New tools

```
annotation_create_import_job(profile_id, query, options?)
annotation_create_export_job(annotation_set_id, format, options?, destination_profile_id?)
annotation_get_conversion_report(job_id)
annotation_list_dead_letter_jobs(tenant_id?)
annotation_retry_job(job_id)
```

## Tests to Add

```
tests/annotation/test_job_service.py
    - test_create_import_job_returns_job_id
    - test_get_job_status_reads_real_table
    - test_get_job_status_stub_removed
    - test_cancel_job_transitions_to_failed
    - test_job_state_machine_queued_to_succeeded
    - test_job_retry_increments_retry_count
    - test_dead_letter_after_max_retries
    - test_get_task_still_returns_annotation_set   # regression: alias preserved

tests/annotation/test_audit_log.py
    - test_audit_log_written_on_state_change
    - test_audit_log_append_only
    - test_audit_log_has_tenant_id
```

## Acceptance Criteria

- [ ] `get_job_status` reads from jobs table (not hardcoded "succeeded")
- [ ] `cancel_job` transitions state to failed (not hardcoded "not_cancelable")
- [ ] Every job state transition writes an AuditLog entry
- [ ] Dead-letter jobs visible via MCP tool
- [ ] `retry_dead_letter_job` resets state to queued
- [ ] `get_task(annotation_set_id)` still works (alias preserved, not renamed)
- [ ] `list_tasks()` still works (alias preserved)
- [ ] `npm run test:python` fully green
