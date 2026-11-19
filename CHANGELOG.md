# Changelog

## 0.2.0

Added experimental Windows support to the VS Code extension and CLI. Preview, apply, and undo sweeps on local NTFS projects, including case-only renames. The engine skips junctions and rejects reserved Windows filenames before making changes.

## 0.1.7

Added a screenshot walkthrough of a `Bob` → `Martin` rename, including the Command Palette shortcuts, folder scope, and diff preview.

## 0.1.6

Shortened the README and updated the Marketplace listing with a worked example of renaming files, folders, and text across naming conventions.

## 0.1.5

Published the VS Code edition under the registered Alex Does IT LLC publisher, `alexdoesitllc`. The CLI and rename behavior are the same as in 0.1.4.

## 0.1.4

First release packaged for Alex Does IT LLC under the MIT License.

- Preview, apply, and undo coordinated filename, folder, and text rewrites from VS Code or the CLI.
- Preserve naming conventions or use regular expressions with capture groups.
- Review file diffs and check for collisions, stale previews, and unsaved editor changes before applying a sweep.
