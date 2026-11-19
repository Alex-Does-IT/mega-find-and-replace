# Mega Find and Replace

Created by **Alex Does IT LLC**. Use the VS Code extension or the `mega-rename` CLI to rename files, folders, and text references in one sweep.

## Installation

The extension and CLI require macOS or Linux with Python 3.9 or newer. On Linux the engine uses GNU `cp` and `renameat2`.

For VS Code, download the `.vsix` from the [GitHub releases](https://github.com/Alex-Does-IT/mega-find-and-replace/releases). In the Command Palette, run **Extensions: Install from VSIX…** and select the downloaded file. If you installed the development extension under `alex-local.mega-find-and-replace`, uninstall that copy when switching to the company release.

For the standalone CLI, clone this repository and run `./mega-rename --help`.

## VS Code

Open **Mega Replace** in the Activity Bar, or press **⇧⌘P** on macOS and run **Mega Replace: Find and Replace**. The view starts in the active workspace folder. Right-click a folder in Explorer and choose **Mega Replace in Folder…** to narrow the scope.

1. Type in **Search** to see matching filenames, folders, and text. Select a result to open it.
2. Enter **Replace** to preview the sweep. Each result shows its final path and the first changed line where applicable. Click an edited file to open its full VS Code diff.
3. Click **Replace All** to apply the reviewed changes. **Undo last sweep** restores the latest sweep in the selected folder, including after a window reload.

Case-aware identifier matching is the default. **Aa** selects exact casing. **.\*** enables Python regex with captured replacements such as `martin$1`. For regex deletion, leave the replacement empty and select **Replace matches with empty text**. **Search options** includes substring matching, exclusion globs, and Git-ignored files.

The extension bundles the CLI and runs in trusted desktop workspaces on macOS and Linux with Python 3.9+ available as `python3`. Results reflect saved files. Replace All checks the preview against disk and asks you to save or revert affected unsaved editors before writing.

## Command line

Rename a term across file names, folder names, and text references under one directory. Run the executable directly with Python 3.9+ on macOS or Linux. It uses the system `cp` (GNU `cp` on Linux) and uses Git's ignore rules when Git is available in a worktree.

```sh
./mega-rename preview /path/to/project Bob Martin --diff
./mega-rename apply   /path/to/project Bob Martin
./mega-rename undo    /path/to/project
```

`preview` lists each edited file and each renamed entry with its final path. Add `--diff` to see the text replacements. `apply` builds a fresh plan from the current tree. The selected directory is the scope root. Renames start at its children.

| Before | After |
| --- | --- |
| `Bob/Bob.txt` | `Martin/Martin.txt` |
| `import { getBob } from "./Bob/BobDoesThis"` | `import { getMartin } from "./Martin/MartinDoesThis"` |
| `bobDoesThis` | `martinDoesThis` |
| `BOB_DOES_THIS` | `MARTIN_DOES_THIS` |
| `bob-does-this` | `martin-does-this` |

## Matching

The same rules apply to paths and text. By default, a match starts and ends at a word, case, or digit boundary. That picks up `getBob`, `Bob2`, and `XMLBob`. Use `--substring` to reach inside ordinary words as well, for example to change `bobcat` to `martincat`.

For a multiword rename, use any conventional spelling for the arguments. A sweep from `OldWidget` to `NewGadget` handles `oldWidget`, `OldWidget`, `old_widget`, `OLD_WIDGET`, `old-widget`, `old.widget`, and `Old Widget` in one pass. Replacement text is emitted once per match.

When one word becomes several, adjacent underscores, hyphens, and camel humps help select the style. For `Bob` to `RedFox`, `bobReads` becomes `redFoxReads` and `BOB_READS` becomes `RED_FOX_READS`. An isolated `bob`, `Bob`, or `BOB` defaults to `red_fox`, `RedFox`, or `RED_FOX`, respectively.

Use `--literal` for an exact, case-sensitive replacement, including punctuation, Unicode terms, or a case-only rename. The convention-aware mode accepts ASCII words and digits. Both modes take terms suitable for a single path component.

```sh
./mega-rename preview ./src 'old.widget' 'new-widget' --literal --diff
./mega-rename preview ./src Bob BOB --literal --diff
```

## Regular expressions

Use `--regex` when a pattern should decide which occurrences qualify. For example, this sweep renames `BobV2/bob_v3.txt` to `MartinV2/martin_v3.txt` and updates the same path in source files. Single quotes pass the backslash and `$1` through the shell.

```sh
./mega-rename preview ./src --regex 'bob([_-]?v\d+)' 'martin$1' --diff
./mega-rename apply   ./src --regex 'bob([_-]?v\d+)' 'martin$1'
```

| Match | Replacement |
| --- | --- |
| `bobv1` | `martinv1` |
| `BobV2` | `MartinV2` |
| `BOB_v3` | `MARTIN_v3` |

The pattern is a case-insensitive Python regular expression. It runs independently on each basename and on each eligible file's full decoded text. Write boundaries, separators, and anchors into the pattern wherever you need them. For example, `\bbob(\d{2})\b` selects `Bob42` and skips `Bob420`. Use `(?m)` for line anchors or `(?-i:[A-Z])` for an explicitly uppercase letter.

Captured text is copied verbatim. Literal replacement words borrow the style of the first identifier in the portion of the match outside the copied captures. If the captures cover all the words, the whole match supplies the sample. For example, `old[_-]?widget(\d+)` → `newGadget$1` maps `oldWidget7` to `newGadget7` and `OLD_WIDGET7` to `NEW_GADGET7`. Separators you type in the replacement stay literal. Use `--regex-exact` for case-sensitive matching and literal replacement spelling. It also accepts inline flags such as `(?i)`.

| In the replacement | Result |
| --- | --- |
| `$1`, `$2`, `${1}` | Numbered capture. Use `${1}0` to append a zero to group 1. |
| `${name}` | Named capture from `(?P<name>...)` |
| `$0` | Entire match |
| `$$` | Literal dollar sign |
| `''` as the shell argument | Delete the matched text |

An unmatched optional capture expands to empty text. Backslashes in replacement text are literal. If a replacement would produce an empty, reserved, or colliding basename, or introduce a path separator, backslash, or control character into a basename, planning stops before any writes. A slash in a text reference is fine. Regex sweeps use the same exclusions, journal, and `undo DIRECTORY` command as other sweeps.

## Scope

- Hidden project files and empty folders participate. The scanner skips Git-ignored entries, common dependency and cache locations such as `node_modules` and `.venv`, nested Git worktrees, version-control metadata, symlinks, mounts, and special files.
- `--include-ignored` includes Git-ignored entries and the built-in dependency/cache exclusions. Repeat `--exclude 'GLOB'` to skip matching basenames or root-relative paths. Quote patterns so the shell passes them through.
- Content edits cover UTF-8 and BOM-marked UTF-16/32, preserving encoding, BOM, and line endings. Known binary formats, undecodable data, control-byte data, and files over 16 MiB get filename processing only. Adjust the content limit with `--max-mib 64`. The summary reports skipped counts.
- Renaming a directory carries its children with it, including excluded children. Symbolic link targets can require manual updates. Reference rewriting is textual and includes comments, strings, and documentation. Dynamically assembled references may need a project-specific edit.

## Collisions and recovery

If both `Bob.txt` and `Martin.txt` exist, the sweep stops during planning. The same check covers directories, dangling links, and competing destinations, including case-folded or Unicode-normalized names. Exclusive filesystem moves also protect newly created destinations during apply.

The tool stages edited copies, then moves originals into a private, Git-ignored `.mega-rename/` journal inside the chosen directory. It preserves ordinary permission bits and clears set-user-ID and set-group-ID bits on rewritten copies. Edits to hard-linked files create independent copies at the in-scope paths. Undo restores the original directory entries.

Run `undo` once per sweep, most recent first. It checks the saved originals, edited files, and rename destinations before reversing a completed sweep. A later content edit or occupied destination produces a conflict so you can preserve that work. If a subsequent run reports an interrupted sweep, run `undo` on the same root to recover. A conflicting file must be reconciled before recovery can finish.

Use a local tree you control and pause other writers during apply and undo. Each move is atomic. Readers can observe intermediate paths during the whole sweep. Keep the journal while you need undo. Once all sweeps are complete and you are satisfied with the results, deleting the journal discards their backups and history.

## Verification

Run `python3 -m unittest -v` from this folder. The suite uses disposable directories and exercises nested renames, encodings, permissions, exclusions, collision handling, undo, and interruption recovery.

## License

Copyright (c) 2026 Alex Does IT LLC. Distributed under the [MIT License](LICENSE).
