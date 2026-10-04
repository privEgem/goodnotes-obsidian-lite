# goodnotes-obsidian-lite

## What it does

A small Python learning project that turns new or changed Goodnotes PDF exports
into Markdown notes you can open in an Obsidian vault. It uses file hashes and a
JSON file to remember successful conversions. Export PDFs yourself, then run
the script when you want to update your notes. This is an independent project,
not an official Goodnotes or Obsidian integration.

## How it works

When you run `sync.py`, the script:

1. Scans the input folder for PDFs in sorted order, including `.PDF` files.
2. Calculates a SHA-256 hash for each PDF by reading its bytes in chunks.
3. Loads the previous JSON state.
4. Compares the current hashes with the saved hashes to identify new, changed,
   and unchanged PDFs.
5. Extracts text only from new or changed PDFs, page by page with `pypdf`.
6. Creates Markdown files in the matching folder structure.
7. Saves the new state for the next run, recording successful conversions.

State lives at `<markdown_folder>/.goodnotes-obsidian-lite-state.json`.
A missing state file starts fresh; invalid state causes a clear error.
An unreadable or broken PDF is reported and returns a non-zero exit code.
Other PDFs can still succeed. Failed files keep their last successful hash,
if any, so the next run tries them again.

`--dry-run` performs the scan, hashing, and comparison, then shows what would
change without writing Markdown or updating the state file. It creates no output
directory, does not extract text, and makes no Gemini calls.

## Quick start

Use Python **3.10+**. Download or clone this repository and open a terminal inside
its folder. These commands work in PowerShell and on macOS/Linux:

```text
python -m venv .venv
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

On macOS/Linux, use `source .venv/bin/activate` instead. Then:

```text
python -m pip install -r requirements.txt
python sync.py pdfs notes --dry-run
python sync.py pdfs notes
```

Put exported PDFs in `pdfs` first. Replace `notes` with your vault folder if you
want notes there; quote paths containing spaces. Some systems use `python3`
instead of `python`. For core sync alone, `python -m pip install pypdf` is enough.
No global installation or configuration file is needed.

Run the offline checks:

```text
python -m py_compile sync.py gemini_summary.py
python -m unittest discover -s tests -v
```

## Example

```text
pdfs/                             notes/
  chemistry/                        chemistry/
    redox.pdf                         redox.md
  maths.PDF                         maths.md
                                    .goodnotes-obsidian-lite-state.json
```

Each note includes the PDF filename as its heading, its relative source path,
its SHA-256 hash, and extracted text. A textless PDF creates a note explaining
that this version has no OCR. Running again skips files with unchanged hashes.

## Optional Gemini summary

`gemini_summary.py` sends an existing note's text to Google only when you run it.
It prints a study summary without changing the note. It uses your environment
API key, defaults to `gemini-3.8-flash`, and accepts `--model` for another available
model. Requests have one attempt, with no automatic retry.

As of October 2026, you can create a Gemini API key in **Google AI Studio** without
paying. Google offers a Free Tier for supported models, including free input and
output usage for `gemini-3.8-flash`, subject to its usage limits. You can try this
example without enabling paid billing while staying within those limits.
Upgrading to paid usage requires setting up billing. Limits, model availability,
and pricing can change; check [Google's pricing page](https://ai.google.dev/gemini-api/docs/pricing)
and [API-key documentation](https://ai.google.dev/gemini-api/docs/api-key).

Google states that Free Tier content may be used to improve its products.
Do not send private or sensitive notes unless you are comfortable sharing that
content with Google. Simple setup: [Gemini API guide](docs/GEMINI_API.md).

## Limitations

- Exported PDFs must contain extractable text for meaningful conversion.
- No OCR and no handwriting recognition.
- No live Goodnotes API integration, background watcher, or automatic exports.
- No automatic Markdown deletion when PDFs disappear; their state entries disappear.
- One-way PDF -> Markdown only. Source changes overwrite the corresponding note.
- Unchanged PDFs are skipped even if their Markdown was manually changed or removed.
- PDF layouts, tables, and images are not preserved; extracted text can be imperfect.
- PDFs must map to distinct Markdown paths, including when case is ignored.
- Run one sync at a time; simultaneous runs are not supported.
- Gemini is optional and not used by the core sync.

## How the code is organized

`sync.py` uses plain functions:

- `find_pdfs` lists inputs; `sha256_file` fingerprints their bytes in chunks.
- `load_state` checks JSON; `save_state` writes a temporary file, then replaces state.
- `classify_pdf` compares a path and hash with the previous record.
- `extract_text` reads PDF pages; tests replace this function with sample text.
- `render_markdown` builds a note from the title, source, hash, and text.
- `sync_folder` connects those steps and records only successful conversions.
- `main` reads command-line arguments and turns errors into an exit code.

`gemini_summary.py` is a separate optional example. `tests/test_sync.py` uses
standard-library `unittest`, temporary folders, and mocked extraction. Tests
need no network or API key. The project is licensed under [MIT](LICENSE).
