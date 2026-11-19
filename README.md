# Mega Find and Replace

Rename files, folders, and the text that refers to them in one pass. Pick a directory and enter `JobQueue` → `WorkerPool` once. The tool keeps the casing and separators each match already uses.

| Before | After |
| --- | --- |
| `src/job-queue/JobQueue.ts` | `src/worker-pool/WorkerPool.ts` |
| `import { jobQueue } from "./job-queue/JobQueue"` | `import { workerPool } from "./worker-pool/WorkerPool"` |
| `job_queue_size` | `worker_pool_size` |
| `JOB_QUEUE_SIZE` | `WORKER_POOL_SIZE` |

The extension and CLI run on **macOS and Linux** with **Python 3.9+** available as `python3`. Linux also requires GNU `cp` and `renameat2`.

## In VS Code

Install **Mega Find and Replace**, then right-click the folder you want to search in Explorer and choose **Mega Replace in Folder…**. Enter the old and new names to see the proposed paths. Click an edited file to review its diff, then choose **Replace All**. **Undo last sweep** works even after you reopen VS Code. [Install from the Marketplace](https://marketplace.visualstudio.com/items?itemName=alexdoesitllc.mega-find-and-replace) · [Download a VSIX](https://github.com/Alex-Does-IT/mega-find-and-replace/releases/latest)

## From the terminal

Clone this repo and preview the same rename in a neighboring project.

```sh
./mega-rename preview ../my-project JobQueue WorkerPool --diff
```

When the diff looks right, run `./mega-rename apply ../my-project JobQueue WorkerPool`. To roll it back, run `./mega-rename undo ../my-project`.

By default, `JobQueue` matches inside `getJobQueue` at the capital J. Use `--substring` to match inside ordinary words, `--literal` for exact text, or `--regex` for Python patterns with captures such as `$1`. Run `./mega-rename preview --help` for all matching and exclusion options.

## What a sweep touches

- The selected folder is the boundary. Renames start with its children. The scan respects Git ignore rules and skips symlinks and common dependency folders.
- Text matches include imports, strings, comments, and docs. By default, binary files and files over 16 MiB can still be renamed, but their contents are skipped.
- If two filenames would collide, the sweep stops before writing. Originals are saved in `.mega-rename/` inside the selected folder. Keep it for undo. If an edited file changes again, undo reports the conflict.

## Local development

Run `python3 -m unittest -v` for the CLI tests. To try extension changes, open this checkout in VS Code and press **F5**. Open a disposable folder in the **Extension Development Host** and try a rename and undo. After editing the source, run **Developer: Reload Window** in that window.

Created by **Alex Does IT LLC**. [MIT License](LICENSE)
