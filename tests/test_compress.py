"""Run: python tests/test_compress.py"""

from __future__ import annotations

import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image
from pypdf import PdfReader, PdfWriter

from compress_pdfs import (
    compress_file,
    fmt_bytes,
    max_bytes_from_mb,
    run,
)


def assert_true(cond: bool, label: str) -> None:
    if not cond:
        raise AssertionError(label)
    print(f"  ok  {label}")


def make_heavy_pdf(path: Path, pages: int = 3, px: int = 1600) -> None:
    writer = PdfWriter()
    for i in range(pages):
        raw = os.urandom(px * px * 3)
        img = Image.frombytes("RGB", (px, px), raw)
        buf = BytesIO()
        img.save(buf, format="PDF", quality=95)
        buf.seek(0)
        writer.add_page(PdfReader(buf).pages[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)
    writer.close()


def make_tiny_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)
    writer.close()


def test_fmt_and_limit() -> None:
    assert_true(fmt_bytes(2048).endswith("KB"), "formats kilobytes")
    assert_true("MB" in fmt_bytes(2 * 1024 * 1024), "formats megabytes")
    assert_true(max_bytes_from_mb(2.0) == 2 * 1024 * 1024, "2 MB in bytes")


def test_already_small_is_copied() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "small.pdf"
        dest = tmp_path / "out" / "small.pdf"
        make_tiny_pdf(src)
        result = compress_file(src, dest, limit=2 * 1024 * 1024)
        assert_true(result.ok, "tiny pdf succeeded")
        assert_true(result.method == "copied", f"tiny pdf copied, got {result.method}")
        assert_true(dest.exists(), "tiny pdf written")
        assert_true(len(PdfReader(str(dest)).pages) == 1, "tiny pdf page count kept")


def test_heavy_pdf_fits_under_2mb() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "heavy.pdf"
        dest = tmp_path / "out" / "heavy.pdf"
        make_heavy_pdf(src, pages=3, px=1600)
        original = src.stat().st_size
        assert_true(original > 2 * 1024 * 1024, f"fixture is over 2 MB ({fmt_bytes(original)})")
        result = compress_file(src, dest, limit=2 * 1024 * 1024)
        assert_true(result.ok, "heavy pdf succeeded")
        assert_true(dest.exists(), "heavy pdf written")
        assert_true(result.final <= 2 * 1024 * 1024, f"result {fmt_bytes(result.final)} <= 2 MB")
        assert_true(result.final < original, "result smaller than original")
        assert_true(len(PdfReader(str(dest)).pages) == 3, "page count preserved")
        print(f"       {fmt_bytes(original)} -> {fmt_bytes(result.final)} via {result.method}")


def test_folder_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        incoming = tmp_path / "to_compress"
        outgoing = tmp_path / "compressed"
        make_tiny_pdf(incoming / "keep.pdf")
        make_heavy_pdf(incoming / "big.pdf", pages=2, px=1400)
        code = run(incoming, outgoing, max_mb=2.0)
        assert_true(code == 0, "folder run exit 0")
        assert_true((outgoing / "keep.pdf").exists(), "small file copied")
        assert_true((outgoing / "big.pdf").exists(), "big file compressed")
        assert_true(
            (outgoing / "big.pdf").stat().st_size <= 2 * 1024 * 1024,
            "folder run respects 2 MB",
        )


if __name__ == "__main__":
    print("Compress tests")
    test_fmt_and_limit()
    test_already_small_is_copied()
    test_heavy_pdf_fits_under_2mb()
    test_folder_run()
    print("All compress tests passed.")
