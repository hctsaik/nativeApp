# Design: Module Import And Release Pipeline

## Package Format

The first supported package is a zip containing either root files or one root
folder:

```text
module_012/
  plugin.yaml
  012_input.py
  012_process.py
  012_output.py
  README.md
```

Only UTF-8 text files are accepted. The first release allows `.py`, `.yaml`,
`.yml`, `.md`, `.txt`, and `.html`. Executables, shell scripts, native
extensions, nested paths, absolute paths, and `..` path segments are rejected.

## Import Flow

1. Upload zip.
2. Analyze in memory without extracting into `scripts/`.
3. Validate manifest, naming, file size/count, compression ratio, and Python AST.
4. Show report with errors, file list, hash, and active snapshot diff.
5. Import as a DB snapshot with `source='upload'` and Prod visibility off.

Existing module IDs require an explicit update choice. Existing versions cannot
be imported again.

## Release Flow

Creating a snapshot and exposing a module in Prod are separate actions:

- `Create snapshot` writes an active snapshot and leaves Prod visibility off.
- `Release to Prod` turns on Prod visibility after readiness checks pass.
- `Rollback` switches active snapshot and records audit.

## New Module Flow

The scaffold workflow creates the next available `module_NNN` folder with
`plugin.yaml`, input/process/output skeletons, and README. It also creates a
catalog row with Dev visibility on and Prod visibility off.

## Security Rules

Uploaded packages are not executed during import. Dependency installation is not
supported. Basic AST scanning blocks subprocess/socket imports, dynamic code
execution, shell calls, and Streamlit imports from the process layer.
