# Data Connector Specification

## ADDED Requirements

### Requirement: Connector abstraction for data source independence

The annotation workflow SHALL access image items and write annotation results
through a `DataConnector` interface rather than directly reading the local
filesystem or SQLite manifest.

#### Scenario: Local file mode with no configuration

- WHEN no `connector.yaml` file is present alongside the module
- THEN the system SHALL activate `LocalFileConnector` automatically
- AND all existing module behavior SHALL remain identical to before this change

#### Scenario: SQL connector is configured

- WHEN `connector.yaml` specifies `type: sql`
- THEN the system SHALL pull image metadata from the configured SQL database
- AND SHALL push annotation results back to the configured SQL table
- AND SHALL NOT require any module code changes

#### Scenario: REST connector is configured

- WHEN `connector.yaml` specifies `type: rest`
- THEN the system SHALL fetch image metadata from the REST endpoint
- AND SHALL push annotation results via the batch push endpoint
- AND SHALL download images to a local cache directory before annotation begins

#### Scenario: Custom connector is configured

- WHEN `connector.yaml` specifies `type: custom` with a `module` and `class`
- THEN the system SHALL load the class via `importlib` and use it as the connector
- AND the class SHALL implement `PullConnector` and `PushConnector` interfaces

### Requirement: Image transfer strategy

The connector SHALL not use base64 encoding for image transfer.

#### Scenario: Shared-mount image access

- WHEN the image root is accessible as a shared filesystem mount
- THEN the connector SHALL create a symlink to the original file
- AND SHALL NOT copy the image data

#### Scenario: Remote image download

- WHEN images must be downloaded from a URL
- THEN the connector SHALL use streaming HTTP GET
- AND SHALL skip re-download if a local cached file exists and the md5 hash matches

### Requirement: Credentials are never stored in module config

Connector credentials SHALL be stored only in `CIM_LOG_DIR/secrets/connector_creds.json`
and injected as environment variables by the engine.

#### Scenario: DSN or token is needed at runtime

- WHEN a module needs the SQL DSN or REST Bearer token
- THEN the value SHALL be read from the environment variable named in `connector.yaml`
- AND SHALL NOT be read from `plugin.yaml`, module config JSON, or any file
  committed to the repository

### Requirement: Partial push failure does not crash the module

#### Scenario: Some annotations fail to push

- WHEN `push_batch` is called and some items fail
- THEN the method SHALL return a `PushResult` per item
- AND failed items SHALL remain in `sync_queue` with status `pending`
- AND the module SHALL surface which items failed without raising an exception

### Requirement: Connection error leaves sync queue intact

#### Scenario: Network is unavailable during push

- WHEN a `ConnectionError` is raised during `push_batch`
- THEN all items SHALL remain in `sync_queue` with status `pending`
- AND the module SHALL continue operating normally in offline mode

### Requirement: Conflict detection before push

#### Scenario: Remote was modified after local session started

- WHEN `check_remote_version` returns a `remote_updated_at` value that is later
  than the local annotation session start time
- THEN the item SHALL be marked as `conflict` in `sync_queue`
- AND SHALL NOT be pushed until the user resolves the conflict

### Requirement: ConnectorFactory falls back safely

#### Scenario: connector.yaml is absent

- WHEN `ConnectorFactory.build()` is called with no path or a non-existent path
- THEN it SHALL return a `LocalFileConnector` for both pull and push
- AND SHALL NOT raise an exception
