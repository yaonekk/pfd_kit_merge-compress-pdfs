"""Run: python tests/test_grouping.py"""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from merge_pdfs import group_key, natural_key, group_loose_pdfs, plan_jobs


def assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}\n  expected: {expected!r}\n  actual:   {actual!r}")
    print(f"  ok  {label}")


def test_group_key_strips_page_numbers() -> None:
    assert_eq(group_key("Contract_John_1"), "Contract_John", "strip _1")
    assert_eq(group_key("Contract_John_2"), "Contract_John", "strip _2")
    assert_eq(group_key("Invoice_Acme_page1"), "Invoice_Acme", "strip _page1")
    assert_eq(group_key("Invoice_Acme_page2"), "Invoice_Acme", "strip _page2")
    assert_eq(group_key("Report (1)"), "Report", "strip (1)")
    assert_eq(group_key("Report (2)"), "Report", "strip (2)")
    assert_eq(group_key("Notes"), "Notes", "leave unique name")
    assert_eq(group_key("Scan_p03"), "Scan", "strip _p03")
    assert_eq(group_key("File-part-10"), "File", "strip -part-10")


def test_natural_sort_orders_numbers() -> None:
    names = ["a_10.pdf", "a_2.pdf", "a_1.pdf"]
    assert_eq(
        sorted(names, key=natural_key),
        ["a_1.pdf", "a_2.pdf", "a_10.pdf"],
        "natural sort 1, 2, 10",
    )


def test_loose_files_group_together() -> None:
    tmp = Path(tempfile.mkdtemp())
    files = [
        tmp / "Invoice_Acme_page2.pdf",
        tmp / "Invoice_Acme_page1.pdf",
        tmp / "Invoice_Acme_page10.pdf",
        tmp / "Solo.pdf",
    ]
    grouped = group_loose_pdfs(files)
    assert_eq(
        [p.name for p in grouped["Invoice_Acme"]],
        ["Invoice_Acme_page1.pdf", "Invoice_Acme_page2.pdf", "Invoice_Acme_page10.pdf"],
        "invoice pages grouped and ordered",
    )
    assert_eq([p.name for p in grouped["Solo"]], ["Solo.pdf"], "solo file stays alone")


def test_subfolders_become_their_own_jobs() -> None:
    tmp = Path(tempfile.mkdtemp())
    client = tmp / "ClientA"
    client.mkdir()
    (tmp / "Alpha_1.pdf").write_bytes(b"%PDF")
    (tmp / "Alpha_2.pdf").write_bytes(b"%PDF")
    (client / "intro.pdf").write_bytes(b"%PDF")
    (client / "body.pdf").write_bytes(b"%PDF")

    jobs = {name: [p.name for p in paths] for name, paths in plan_jobs(tmp)}
    assert_eq(jobs["Alpha"], ["Alpha_1.pdf", "Alpha_2.pdf"], "loose files grouped")
    assert_eq(jobs["ClientA"], ["body.pdf", "intro.pdf"], "folder becomes one job")


if __name__ == "__main__":
    print("Grouping tests")
    test_group_key_strips_page_numbers()
    test_natural_sort_orders_numbers()
    test_loose_files_group_together()
    test_subfolders_become_their_own_jobs()
    print("All grouping tests passed.")
