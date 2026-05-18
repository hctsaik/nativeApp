---
name: source-code-packager
description: Package any software project into a clean, verified source archive. Use when asked to make source zips, release handoff packages, email/Gmail-safe packages, exclude generated artifacts, rename blocked attachment types, add extraction/restore instructions, or verify that an archive can be used after extraction.
---

# Source Code Packager

## Purpose

Create distributable source-code archives for any project: Python, JavaScript/TypeScript, C/C++, C#, Java, data tools, desktop apps, and mixed repos. The package should be small, reviewable, and usable after extraction.

Prefer a source package over a runtime package unless the user explicitly asks for bundled dependencies, installers, models, media, compiled binaries, or generated outputs.

## Default Workflow

1. Inspect the project root with `rg --files` and shallow directory listings.
2. Classify files by intent:
   - Include source code, tests, config, docs, manifests/lockfiles, build definitions, launch scripts, schemas, migrations, and small fixtures needed to run or understand the project.
   - Exclude local environments, dependency folders, caches, logs, build output, temporary data, generated reports, large media, model weights, generated frames, previous packages, and user/private local files.
3. Choose packaging mode:
   - Use explicit includes for normal projects with clear source directories.
   - Use `--include-all` only when the repo layout is unusual and the exclude rules are enough to avoid generated artifacts.
4. Verify the zip:
   - Reopen it and list entries.
   - Check required entry points exist.
   - Confirm excluded directories/extensions are absent.
   - Extract to a temporary folder.
   - Run syntax checks when possible, such as `python -m compileall -q`.
5. Report the final zip path, what was included/excluded, and any remaining setup requirements.

## Email/Gmail-Safe Packages

Use Gmail-safe mode when the user says Gmail blocks the package, asks for email-friendly output, or the archive contains blocked executable/script extensions.

Gmail blocks several file types even inside archives. Common project offenders include `.bat`, `.cmd`, `.exe`, `.js`, `.mjs`, `.ps1`, `.vbs`, `.jar`, `.msi`, `.dll`, `.lnk`, and disk images. Do not rely on nested zip, renaming the outer zip, or encryption to bypass this.

In Gmail-safe mode, keep blocked files but rename them inside the archive by appending `.txt`:

```text
setup.bat   -> setup.bat.txt
run_gui.bat -> run_gui.bat.txt
build.bat   -> build.bat.txt
src/app.js  -> src/app.js.txt
```

Add both:

- `README_AFTER_EXTRACT.txt`: concise instructions explaining why files were renamed and how to restore them.
- `restore_gmail_safe_filenames.py`: a Python helper that renames blocked files back to their original names after extraction.

After building a Gmail-safe zip, scan archive entries against the blocked extension list and require zero matches before presenting it as Gmail-safe.

## Bundled Script

Prefer running `scripts/package_source_zip.py` for repeatable packaging. It supports:

- Clean source zip creation.
- Optional `--gmail-safe` script renaming.
- README and restore helper injection.
- Zip entry validation.
- Optional extraction plus Python compile validation.

Example from a project root:

```powershell
python C:\Users\hctsa\.codex\skills\source-code-packager\scripts\package_source_zip.py --root . --gmail-safe --name MyProject_source_gmail_safe
```

For a project with a standard layout, default includes often work. For a custom layout, pass explicit includes:

```powershell
python C:\Users\hctsa\.codex\skills\source-code-packager\scripts\package_source_zip.py --root C:\code\myapp --gmail-safe --include src,docs,tests,README.md,package.json,pyproject.toml --required README.md
```

For unusual repos where most files are source and generated artifacts are well named:

```powershell
python C:\Users\hctsa\.codex\skills\source-code-packager\scripts\package_source_zip.py --root C:\code\myapp --gmail-safe --include-all --exclude-dir data --exclude-dir outputs
```

If the script needs adjustment for a repo, patch the script or pass explicit include/exclude arguments rather than hand-writing a one-off archive command.

## Validation Notes

Do not claim a package is usable just because a zip file exists. At minimum, verify entry count and contents. For Python projects, `compileall` catches missing syntax/runtime-parser issues without launching the GUI. For apps that need external dependencies, clearly say the source package still requires dependency installation after extraction.
