"""Convert new or changed PDF exports to Markdown, using a small JSON state."""

import argparse
import hashlib
import json
from pathlib import Path
import sys


STATE_FILENAME = ".goodnotes-obsidian-lite-state.json"
NO_TEXT_WARNING = "No extractable text found. This lite version does not include OCR."


def find_pdfs(folder):
    """Find PDFs in a predictable order, including uppercase extensions."""
    return sorted(
        (path for path in folder.rglob("*")
         if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.relative_to(folder).as_posix(),
    )


def sha256_file(path):
    """Hash chunks instead of loading the whole PDF into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_state(path):
    """Missing state is empty; invalid JSON or structure is an error."""
    if not path.exists():
        return {"files": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"Invalid state file {path}: {error}") from error
    if not isinstance(state, dict) or not isinstance(state.get("files", {}), dict):
        raise ValueError(f"Invalid state file {path}: expected a files object")
    files = state.get("files", {})
    for name, entry in files.items():
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("sha256"), str)
                or not isinstance(entry.get("markdown"), str)):
            raise ValueError(f"Invalid state file {path}: invalid entry for {name}")
    return {"files": files}


def save_state(path, state):
    """Replace state only after a complete UTF-8 JSON write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def classify_pdf(name, digest, files):
    """The relative path identifies a PDF; its hash detects changed bytes."""
    if name not in files:
        return "NEW"
    return "UNCHANGED" if files[name]["sha256"] == digest else "CHANGED"


def extract_text(path):
    """Read pages in order. Kept separate so tests can mock extraction."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()


def render_markdown(relative_pdf, digest, text):
    """Keep source details and extracted text easy to read."""
    body = text.strip() or f"> {NO_TEXT_WARNING}"
    return (
        f"# {relative_pdf.stem}\n\n"
        f"Source: `{relative_pdf.as_posix()}`\n\n"
        f"SHA-256: `{digest}`\n\n---\n\n{body}\n"
    )


def sync_folder(pdf_folder, markdown_folder, dry_run=False):
    """Scan, hash, compare, then write successful conversions and their state."""
    if not pdf_folder.is_dir():
        raise ValueError(f"Input directory does not exist or is not a directory: {pdf_folder}")
    pdfs = find_pdfs(pdf_folder)
    destinations = [pdf.relative_to(pdf_folder).with_suffix(".md").as_posix().casefold()
                    for pdf in pdfs]
    if len(destinations) != len(set(destinations)):
        raise ValueError("PDFs map to the same Markdown path; rename a conflicting PDF")
    hashes = {}
    failed = set()
    for pdf in pdfs:
        name = pdf.relative_to(pdf_folder).as_posix()
        try:
            hashes[name] = sha256_file(pdf)
        except OSError as error:
            print(f"ERROR {name}: {error}", file=sys.stderr)
            failed.add(name)

    state_path = markdown_folder / STATE_FILENAME
    previous = load_state(state_path)["files"]
    # Retain the last successful hash on failure, so a later run tries again.
    current = {name: previous[name] for name in failed if name in previous}
    for pdf in pdfs:
        relative = pdf.relative_to(pdf_folder)
        name = relative.as_posix()
        if name not in hashes:
            continue
        digest = hashes[name]
        markdown = relative.with_suffix(".md")
        status = classify_pdf(name, digest, previous)
        print(f"{status} {name}")
        entry = {"sha256": digest, "markdown": markdown.as_posix()}
        if status == "UNCHANGED":
            current[name] = entry
            continue
        print(f"{'Would write' if dry_run else 'Writing'} {markdown.as_posix()}")
        if dry_run:
            continue  # Everything below this point writes files.
        try:
            text = extract_text(pdf)
            output = markdown_folder / markdown
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(render_markdown(relative, digest, text), encoding="utf-8")
            current[name] = entry
        except Exception as error:
            print(f"ERROR {name}: {type(error).__name__}: {error}", file=sys.stderr)
            failed.add(name)
            if name in previous:
                current[name] = previous[name]

    if not dry_run:
        save_state(state_path, {"files": current})
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_folder", type=Path)
    parser.add_argument("markdown_folder", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    args = parser.parse_args(argv)
    try:
        return sync_folder(args.pdf_folder, args.markdown_folder, args.dry_run)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
