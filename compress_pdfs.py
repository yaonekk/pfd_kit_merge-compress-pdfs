"""
PDF Kit — compress PDFs so each file fits under a size you choose (MB or KB).

Drop files into the to_compress/ folder, then run this script.
Results are written to compressed/ (originals are left untouched).

Size examples: 2mb, 1.5 MB, 500kb, 500ko, 800 (a bare number = MB)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment, misc]

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover
    pdfium = None

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "to_compress"
DEFAULT_OUTPUT = ROOT / "compressed"
DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB

# Downscale + JPEG quality, tried in order until the file fits.
IMAGE_PASSES: list[tuple[int, int]] = [
    (1600, 72),
    (1400, 62),
    (1200, 52),
    (1000, 42),
    (800, 36),
    (640, 30),
    (512, 25),
]

# Render scale (1.0 = 72 DPI) + JPEG quality. Last resort; pages become images.
RASTER_PASSES: list[tuple[float, int]] = [
    (1.4, 70),
    (1.1, 60),
    (0.9, 50),
    (0.75, 42),
    (0.6, 36),
    (0.5, 30),
    (0.4, 25),
]

# Accepted units -> multiplier in bytes (1 KB = 1024 B). "ko"/"mo" = French spelling.
UNITS: dict[str, int] = {
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "ko": 1024,
    "kib": 1024,
    "m": 1024 * 1024,
    "mb": 1024 * 1024,
    "mo": 1024 * 1024,
    "mib": 1024 * 1024,
}


@dataclass
class CompressResult:
    src: Path
    dest: Path | None
    original: int
    final: int
    method: str
    warning: str = ""

    @property
    def ok(self) -> bool:
        return self.dest is not None and self.final > 0


def natural_key(value: str) -> list[int | str]:
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", value)]


def fmt_bytes(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def parse_size(text: str) -> int:
    """Turn '2mb', '500 KB', '500ko', '1,5mb' or '2' (= MB) into a byte count."""
    match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)\s*", text)
    if not match:
        raise ValueError(f"Can't read size '{text}'. Try 2mb or 500kb.")
    number = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "mb").lower()
    if unit not in UNITS:
        raise ValueError(f"Unknown unit '{match.group(2)}'. Use KB/KO or MB/MO.")
    size = int(number * UNITS[unit])
    if size < 1:
        raise ValueError("Size must be greater than zero.")
    return size


def argparse_size(text: str) -> int:
    try:
        return parse_size(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def ask_size(default: int = DEFAULT_MAX_BYTES) -> int:
    """Ask the user for the target size; Enter keeps the default."""
    while True:
        try:
            answer = input(f"Max size per PDF (e.g. 2mb, 500kb, 500ko) [{fmt_bytes(default)}]: ").strip()
        except EOFError:
            return default
        if not answer:
            return default
        try:
            return parse_size(answer)
        except ValueError as exc:
            print(f"  {exc}")


def collect_pdfs(input_dir: Path) -> list[Path]:
    return sorted(
        (p for p in input_dir.rglob("*.pdf") if p.is_file()),
        key=lambda p: natural_key(str(p.relative_to(input_dir))),
    )


def find_ghostscript() -> str | None:
    for name in ("gswin64c", "gswin32c", "gs"):
        found = shutil.which(name)
        if found:
            return found
    for root in (Path(r"C:\Program Files\gs"), Path(r"C:\Program Files (x86)\gs")):
        if not root.exists():
            continue
        matches = sorted(root.glob("gs*/bin/gswin64c.exe")) + sorted(root.glob("gs*/bin/gswin32c.exe"))
        if matches:
            return str(matches[-1])
    return None


def open_reader(src: Path) -> PdfReader:
    reader = PdfReader(str(src), strict=False)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise PdfReadError(f"password-protected: {src.name}") from exc
    return reader


def writer_from(src: Path) -> PdfWriter:
    writer = PdfWriter()
    writer.append(open_reader(src))
    return writer


def dumps(writer: PdfWriter) -> bytes:
    buf = BytesIO()
    writer.write(buf)
    writer.close()
    return buf.getvalue()


def lossless_rewrite(src: Path) -> bytes:
    writer = writer_from(src)
    for page in writer.pages:
        try:
            page.compress_content_streams()
        except Exception:
            continue
    try:
        writer.compress_identical_objects()
    except Exception:
        pass
    return dumps(writer)


def prepare_image(im: Image.Image, max_px: int) -> Image.Image:
    if im.mode == "CMYK":
        im = im.convert("RGB")
    elif im.mode == "P":
        im = im.convert("RGBA") if "transparency" in im.info else im.convert("RGB")
    elif im.mode == "1":
        im = im.convert("L")

    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.split()[-1])
        im = bg
    elif im.mode not in ("RGB", "L"):
        im = im.convert("RGB")

    width, height = im.size
    longest = max(width, height)
    if longest > max_px:
        ratio = max_px / longest
        im = im.resize(
            (max(1, int(width * ratio)), max(1, int(height * ratio))),
            Image.Resampling.LANCZOS,
        )
    return im


def recompress_images(src: Path, max_px: int, quality: int) -> bytes | None:
    if Image is None:
        return None
    writer = writer_from(src)
    seen: set[tuple[int, int]] = set()
    for page in writer.pages:
        try:
            images = list(page.images)
        except Exception:
            images = []
        for img in images:
            ref = img.indirect_reference
            if ref is not None:
                key = (ref.idnum, int(getattr(ref, "generation", 0)))
                if key in seen:
                    continue
                seen.add(key)
            pil = img.image
            if pil is None or max(pil.size) < 128:
                continue
            try:
                img.replace(prepare_image(pil, max_px), quality=quality, optimize=True)
            except Exception:
                continue
        try:
            page.compress_content_streams()
        except Exception:
            pass
    try:
        writer.compress_identical_objects()
    except Exception:
        pass
    return dumps(writer)


def rasterize(src: Path, scale: float, quality: int) -> bytes | None:
    if pdfium is None or Image is None:
        return None
    doc = pdfium.PdfDocument(str(src))
    writer = PdfWriter()
    try:
        for index in range(len(doc)):
            page = doc[index]
            try:
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil().convert("RGB")
                buf = BytesIO()
                pil.save(
                    buf,
                    format="PDF",
                    resolution=72.0 * scale,
                    quality=quality,
                    optimize=True,
                )
                buf.seek(0)
                writer.add_page(PdfReader(buf).pages[0])
            finally:
                page.close()
        return dumps(writer)
    finally:
        doc.close()


def ghostscript_compress(src: Path, extra_args: list[str]) -> bytes | None:
    gs = find_ghostscript()
    if not gs:
        return None
    with tempfile.TemporaryDirectory(prefix="pdf_gs_") as tmp:
        dest = Path(tmp) / "out.pdf"
        cmd = [
            gs,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            *extra_args,
            f"-sOutputFile={dest}",
            str(src),
        ]
        kwargs: dict = {"check": False, "timeout": 180, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(cmd, **kwargs)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0 or not dest.exists():
            return None
        data = dest.read_bytes()
        return data or None


def keep_better(best: bytes | None, candidate: bytes | None) -> bytes | None:
    if candidate is None:
        return best
    if best is None or len(candidate) < len(best):
        return candidate
    return best


def compress_bytes(src: Path, limit: int) -> tuple[bytes, str, str]:
    """
    Return (pdf_bytes, method, warning).
    method is one of: original, lossless, ghostscript, images, raster, best_effort.
    """
    original = src.read_bytes()
    best: bytes | None = original
    warning = ""

    try:
        best = keep_better(best, lossless_rewrite(src))
        if best is not None and len(best) <= limit:
            method = "lossless" if len(best) < len(original) else "original"
            return best, method, warning
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfReadError(str(exc)) from exc

    gs_passes = [
        ["-dPDFSETTINGS=/ebook"],
        ["-dPDFSETTINGS=/screen"],
        [
            "-dPDFSETTINGS=/screen",
            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dColorImageResolution=96",
            "-dGrayImageResolution=96",
        ],
        [
            "-dPDFSETTINGS=/screen",
            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dColorImageResolution=72",
            "-dGrayImageResolution=72",
        ],
    ]
    for args in gs_passes:
        candidate = ghostscript_compress(src, args)
        best = keep_better(best, candidate)
        if candidate is not None and len(candidate) <= limit:
            return candidate, "ghostscript", warning

    for max_px, quality in IMAGE_PASSES:
        try:
            candidate = recompress_images(src, max_px=max_px, quality=quality)
        except Exception:
            candidate = None
        best = keep_better(best, candidate)
        if candidate is not None and len(candidate) <= limit:
            return candidate, "images", warning

    for scale, quality in RASTER_PASSES:
        try:
            candidate = rasterize(src, scale=scale, quality=quality)
        except Exception:
            candidate = None
        best = keep_better(best, candidate)
        if candidate is not None and len(candidate) <= limit:
            return candidate, "raster", "flattened to images to hit the size cap"

    assert best is not None
    over = f"still {fmt_bytes(len(best))} after best effort (limit {fmt_bytes(limit)})"
    return best, "best_effort", over


def compress_file(src: Path, dest: Path, limit: int, force: bool = False) -> CompressResult:
    original = src.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)

    if original <= limit and not force:
        shutil.copy2(src, dest)
        return CompressResult(src, dest, original, dest.stat().st_size, "copied")

    try:
        data, method, warning = compress_bytes(src, limit)
    except (PdfReadError, OSError, ValueError) as exc:
        return CompressResult(src, None, original, original, "failed", str(exc))

    # Never write a larger file than the original.
    if len(data) >= original and original <= limit:
        shutil.copy2(src, dest)
        return CompressResult(src, dest, original, dest.stat().st_size, "copied")

    dest.write_bytes(data)
    return CompressResult(src, dest, original, len(data), method, warning)


def run(
    input_dir: Path,
    output_dir: Path,
    limit: int = DEFAULT_MAX_BYTES,
    preview: bool = False,
    force: bool = False,
) -> int:
    if not input_dir.exists():
        print(f"Input folder not found: {input_dir}")
        print("Create it and drop your PDFs inside.")
        return 1

    files = collect_pdfs(input_dir)
    if not files:
        print(f"No PDFs found in {input_dir}")
        print("Put PDF files in that folder, then run again.")
        return 1

    print(f"Input : {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Limit : {fmt_bytes(limit)}")
    print()

    if preview:
        for path in files:
            size = path.stat().st_size
            rel = path.relative_to(input_dir)
            if size <= limit and not force:
                print(f"  [OK   ] {rel}  {fmt_bytes(size)}  (already under limit)")
            else:
                print(f"  [SHRINK] {rel}  {fmt_bytes(size)}")
        print("\nPreview only. No files written. Run without --preview to compress.")
        return 0

    saved = 0
    failed = 0
    over_limit = 0
    for path in files:
        rel = path.relative_to(input_dir)
        dest = output_dir / rel
        result = compress_file(path, dest, limit=limit, force=force)
        label = rel.as_posix()
        if not result.ok:
            print(f"  failed  {label}  ({result.warning})")
            failed += 1
            continue
        saved += 1
        note = f"{fmt_bytes(result.original)} -> {fmt_bytes(result.final)}  [{result.method}]"
        if result.final > limit:
            over_limit += 1
            print(f"  warn    {label}  {note}")
            if result.warning:
                print(f"          {result.warning}")
        else:
            print(f"  saved   {label}  {note}")
            if result.warning:
                print(f"          {result.warning}")

    print(f"\nDone. {saved} PDF(s) in {output_dir}" + (f", {failed} failed" if failed else ""))
    if over_limit:
        print(f"{over_limit} file(s) could not be reduced under {fmt_bytes(limit)}.")
    return 1 if failed and not saved else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PDF Kit: compress PDFs in to_compress/ to a size you choose (MB or KB).",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Folder that holds the PDFs to compress (default: to_compress/)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Folder for compressed PDFs (default: compressed/)",
    )
    parser.add_argument(
        "-s",
        "--size",
        type=argparse_size,
        default=None,
        help="Max size per file, e.g. 2mb, 500kb, 500ko (bare number = MB). "
        "If omitted, you will be asked.",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=None,
        help="Max size in megabytes (kept for backward compatibility; prefer --size)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show which files need shrinking, without writing anything",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompress even if a file is already under the size limit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.size is not None:
        limit = args.size
    elif args.max_mb is not None:
        limit = max(1, int(args.max_mb * 1024 * 1024))
    elif sys.stdin.isatty():
        limit = ask_size()
        print()
    else:
        limit = DEFAULT_MAX_BYTES

    return run(
        input_dir=args.input.resolve(),
        output_dir=args.output.resolve(),
        limit=limit,
        preview=args.preview,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main())