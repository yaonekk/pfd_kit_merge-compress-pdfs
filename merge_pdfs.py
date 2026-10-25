"""
PDF Kit — merge PDFs by name.

Drop files into the to_merge/ folder, then run this script.
Files that share a name (after stripping page/part numbers) are combined
into one PDF. Each subfolder is merged into a PDF named after that folder.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "to_merge"
DEFAULT_OUTPUT = ROOT / "merged"

# Trailing markers like: _1, -2, page 3, p04, part 2, (1), [12]
TRAILING_INDEX = re.compile(
    r"""
    (?:
        [\s._\-–—]*
        (?:
            page|pages|pg|p|part|pt|copy|vol|volume|
            ch|chapter|sec|section|no|num|number|#
        )?
        [\s._\-–—]*
        (?:
            \(\d+\)
            |\[\d+\]
            |\d+
        )
    )+$
    """,
    re.IGNORECASE | re.VERBOSE,
)

INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*]')


def natural_key(value: str) -> list[int | str]:
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", value)]


def group_key(stem: str) -> str:
    """Turn 'Invoice_Acme_page2' / 'Invoice_Acme_2' into 'Invoice_Acme'."""
    cleaned = TRAILING_INDEX.sub("", stem).strip(" ._-\u2013\u2014")
    return cleaned or stem


def safe_filename(name: str) -> str:
    cleaned = INVALID_WIN_CHARS.sub("_", name).strip(" .")
    return cleaned or "merged"


def collect_pdfs(input_dir: Path) -> tuple[list[Path], dict[str, list[Path]]]:
    """
    Returns:
      - loose PDFs sitting directly in input_dir
      - subfolder name -> PDFs inside that folder (non-recursive)
    """
    loose = sorted(
        (p for p in input_dir.glob("*.pdf") if p.is_file()),
        key=lambda p: natural_key(p.name),
    )
    folders: dict[str, list[Path]] = {}
    for child in sorted(input_dir.iterdir(), key=lambda p: natural_key(p.name)):
        if not child.is_dir() or child.name.startswith("."):
            continue
        pdfs = sorted(
            (p for p in child.glob("*.pdf") if p.is_file()),
            key=lambda p: natural_key(p.name),
        )
        if pdfs:
            folders[child.name] = pdfs
    return loose, folders


def group_loose_pdfs(files: list[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        groups[group_key(path.stem)].append(path)
    for key in groups:
        groups[key].sort(key=lambda p: natural_key(p.name))
    return dict(sorted(groups.items(), key=lambda item: natural_key(item[0])))


def unique_output_path(output_dir: Path, name: str) -> Path:
    candidate = output_dir / f"{safe_filename(name)}.pdf"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        extra = output_dir / f"{safe_filename(name)}_{n}.pdf"
        if not extra.exists():
            return extra
        n += 1


def merge_files(paths: list[Path], dest: Path) -> tuple[int, list[str]]:
    """Write dest from paths. Returns (page_count, skipped_file_messages)."""
    writer = PdfWriter()
    skipped: list[str] = []
    pages = 0

    for path in paths:
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    skipped.append(f"password-protected: {path.name}")
                    continue
            writer.append(reader)
            pages += len(reader.pages)
        except (PdfReadError, OSError, ValueError) as exc:
            skipped.append(f"{path.name} ({exc})")

    if pages == 0:
        return 0, skipped

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        writer.write(handle)
    writer.close()
    return pages, skipped


def plan_jobs(
    input_dir: Path,
) -> list[tuple[str, list[Path]]]:
    loose, folders = collect_pdfs(input_dir)
    jobs: list[tuple[str, list[Path]]] = []

    for name, paths in group_loose_pdfs(loose).items():
        jobs.append((name, paths))

    for folder_name, paths in folders.items():
        jobs.append((folder_name, paths))

    return jobs


def run(
    input_dir: Path,
    output_dir: Path,
    preview: bool = False,
    merge_all: bool = False,
) -> int:
    if not input_dir.exists():
        print(f"Input folder not found: {input_dir}")
        print("Create it and drop your PDFs inside.")
        return 1

    loose, folders = collect_pdfs(input_dir)
    if not loose and not folders:
        print(f"No PDFs found in {input_dir}")
        print("Put PDF files in that folder, or in subfolders, then run again.")
        return 1

    if merge_all:
        all_paths = list(loose)
        for paths in folders.values():
            all_paths.extend(paths)
        all_paths.sort(key=lambda p: natural_key(str(p.relative_to(input_dir))))
        jobs = [("ALL_MERGED", all_paths)]
    else:
        jobs = plan_jobs(input_dir)

    print(f"Input : {input_dir}")
    print(f"Output: {output_dir}")
    print()

    for name, paths in jobs:
        labels = ", ".join(p.name for p in paths)
        action = "MERGE" if len(paths) > 1 else "COPY "
        print(f"  [{action}] {name}.pdf")
        for path in paths:
            rel = path.relative_to(input_dir)
            print(f"           <- {rel}")

    if preview:
        print("\nPreview only. No files written. Run without --preview to merge.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    print()

    written = 0
    for name, paths in jobs:
        dest = unique_output_path(output_dir, name)
        if len(paths) == 1:
            try:
                shutil.copy2(paths[0], dest)
                print(f"Saved {dest.name}  (copy of {paths[0].name})")
                written += 1
                continue
            except OSError:
                # Fall through and rewrite with pypdf.
                pass

        pages, skipped = merge_files(paths, dest)
        if pages:
            print(f"Saved {dest.name}  ({pages} page{'s' if pages != 1 else ''}, {len(paths) - len(skipped)} file(s))")
            written += 1
        else:
            print(f"Skipped {name}: nothing readable to merge")
        for msg in skipped:
            print(f"   warning: {msg}")

    print(f"\nDone. {written} PDF(s) in {output_dir}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PDF Kit: merge PDFs in to_merge/ by shared name (or by subfolder).",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Folder that holds the PDFs to merge (default: to_merge/)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Folder for merged PDFs (default: merged/)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show groups without writing files",
    )
    parser.add_argument(
        "--all",
        dest="merge_all",
        action="store_true",
        help="Merge every PDF into a single ALL_MERGED.pdf, sorted by name",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(
        input_dir=args.input.resolve(),
        output_dir=args.output.resolve(),
        preview=args.preview,
        merge_all=args.merge_all,
    )


if __name__ == "__main__":
    sys.exit(main())
