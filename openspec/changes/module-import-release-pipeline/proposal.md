# Proposal: Module Import And Release Pipeline

## Problem Statement

Management Center can publish modules that already exist on the local
filesystem, but it cannot safely accept a user-provided module package. Packaged
deployments also need a runtime path for adding or updating modules without
copying files into `scripts/`.

## Goals

- Accept module zip packages through Management Center.
- Validate package structure, manifest, file safety, and Python source before
  writing a snapshot.
- Import new or updated modules as active snapshots with Prod visibility off.
- Provide a New Module scaffold workflow for development environments.
- Split release flow so creating a snapshot and turning on Prod are separate
  actions.
- Record import, scaffold, snapshot, release, and rollback actions in audit.

## Non-Goals

- Installing dependencies from uploaded packages.
- Running untrusted module code during import.
- Supporting binary assets or executable files in the first package format.
- Replacing the existing filesystem publish path.
