# PDF Kit

Drop PDFs into a folder. Merge them by name, or shrink them to 2 MB. Originals are never overwritten.

This is a small local toolkit for Windows. You do not need to upload files anywhere.

---

## Contents

1. [What it does](#what-it-does)
2. [Folder map](#folder-map)
3. [One-time setup](#one-time-setup)
4. [Everyday use](#everyday-use)
5. [Merge by name](#merge-by-name)
6. [Compress to 2 MB](#compress-to-2-mb)
7. [Typical workflow](#typical-workflow)
8. [Command reference](#command-reference)
9. [How merging actually groups files](#how-merging-actually-groups-files)
10. [How compression actually shrinks files](#how-compression-actually-shrinks-files)
11. [Troubleshooting](#troubleshooting)
12. [Tests](#tests)

---

## What it does

PDF Kit has two independent tools. You can use either one, or both.

| Tool | You put files in | You run | Results appear in |
|---|---|---|---|
| **Merge** | `to_merge\` | `merge.bat` | `merged\` |
| **Compress** | `to_compress\` | `compress.bat` | `compressed\` |

**Merge** combines PDFs that belong together, based on their filenames (or a subfolder).  
**Compress** takes each PDF on its own and tries to make it **2 MB or smaller**.

Your source files stay where you dropped them. Only the output folders are written.

---

## Folder map

```
pdf_kit/
│
├── to_merge/          Put PDFs here to combine them by name
├── merged/            Combined PDFs land here
│
├── to_compress/       Put PDFs here to shrink them to 2 MB
├── compressed/        Shrunk PDFs land here
│
├── merge.bat          Double-click to merge
├── compress.bat       Double-click to compress
├── merge_pdfs.py      Merge engine
├── compress_pdfs.py   Compress engine
├── requirements.txt   Python libraries
└── README.md          This guide
```

You can ignore the `tests\` folder. That is only for checking that the scripts still work.

---

## One-time setup

You need [Python](https://www.python.org/downloads/) installed. During install, tick **Add python.exe to PATH**.

Then open PowerShell once and run:

```powershell
cd C:\Users\yahya\Desktop\pdf_kit
python -m pip install -r requirements.txt
```

That installs:

- `pypdf` — read, write, and merge PDFs
- `pillow` — recompress images inside PDFs
- `pypdfium2` — last-resort page rendering when a file must be flattened to hit 2 MB

You do not need to repeat this unless you move the project to another PC.

---

## Everyday use

### Merge

1. Copy the PDFs you want combined into `to_merge`.
2. Double-click `merge.bat` (or run `python merge_pdfs.py`).
3. Open `merged` and take the combined files.

### Compress

1. Copy the PDFs you want smaller into `to_compress`.
2. Double-click `compress.bat` (or run `python compress_pdfs.py`).
3. Open `compressed` and take the 2 MB (or smaller) files.

A window stays open so you can read what happened. Press any key to close it.

---

## Merge by name

### Default behaviour

Files sitting **directly** in `to_merge` are grouped by a shared name. Trailing page/part numbers are ignored, then the group is concatenated in natural order (`2` before `10`).

| You drop into `to_merge` | You get in `merged` |
|---|---|
| `licence_1.pdf` + `licence_2.pdf` | `licence.pdf` |
| `Invoice_Acme_page1.pdf` + `Invoice_Acme_page2.pdf` + `Invoice_Acme_page10.pdf` | `Invoice_Acme.pdf` (page 1, then 2, then 10) |
| `Report (1).pdf` + `Report (2).pdf` | `Report.pdf` |
| `Notes.pdf` (only one file with that name) | `Notes.pdf` copied as-is |

### Subfolders = one document

Anything inside a **subfolder** of `to_merge` is treated as one document named after that folder. Files are joined in filename order.

```
to_merge/
  ClientA/
    01_intro.pdf
    02_body.pdf
    03_appendix.pdf
```

becomes `merged\ClientA.pdf` in that order. Prefix with `01_`, `02_`, … if you care about page order.

Loose files and subfolders can be mixed in the same run. They do not interfere with each other.

### Preview before writing

```powershell
python merge_pdfs.py --preview
```

Prints the groups it *would* create. Nothing is written.

### Merge everything into one file

```powershell
python merge_pdfs.py --all
```

Ignores grouping. Every PDF in `to_merge` (including subfolders) is concatenated, sorted by name, into `ALL_MERGED.pdf`.

### Other options

```powershell
python merge_pdfs.py -i D:\inbox -o D:\out
```

Use different folders than the defaults.

If `merged\licence.pdf` already exists from a previous run, the new file is saved as `licence_2.pdf` so nothing is overwritten.

Password-protected files are skipped, with a warning. Other files in the same group are still merged.

---

## Compress to 2 MB

### Default behaviour

Each PDF in `to_compress` (including files in subfolders) is processed on its own.

- Already **2 MB or less** → copied to `compressed` unchanged.
- **Over 2 MB** → shrunk until it fits, then written to `compressed`.
- Folder structure is preserved (`to_compress\school\bac.pdf` → `compressed\school\bac.pdf`).

Originals in `to_compress` are left alone.

### Preview before writing

```powershell
python compress_pdfs.py --preview
```

Shows each file’s size and whether it will be copied or shrunk.

### Different size cap

```powershell
python compress_pdfs.py --max-mb 1.5
```

`2` means 2 mebibytes (2 × 1024 × 1024 bytes), which is the usual “2 MB” upload limit.

### Recompress files that are already small

```powershell
python compress_pdfs.py --force
```

### Other options

```powershell
python compress_pdfs.py -i D:\big-pdfs -o D:\small-pdfs --max-mb 2
```

The console line for each file looks like:

```
saved   licence.pdf  4.20 MB -> 1.18 MB  [images]
```

The tag in brackets is the method that finally fit the file (see [below](#how-compression-actually-shrinks-files)).

If a file has to be flattened to images to hit the cap, a warning is printed. Text may no longer be selectable in that output.

---

## Typical workflow

A common pattern for applications, scans, or school files:

1. Drop the split pieces in `to_merge` (`licence_1.pdf`, `licence_2.pdf`, …).
2. Run **merge**. Pick up `licence.pdf` from `merged`.
3. Copy that combined file into `to_compress`.
4. Run **compress**. Pick up the 2 MB version from `compressed`.

You can skip merge if the file is already one PDF. You can skip compress if size does not matter.

---

## Command reference

Run these from `C:\Users\yahya\Desktop\pdf_kit`, or just double-click the `.bat` files.

| Command | What it does |
|---|---|
| `python merge_pdfs.py` | Merge by name into `merged\` |
| `python merge_pdfs.py --preview` | Show groups, write nothing |
| `python merge_pdfs.py --all` | One `ALL_MERGED.pdf` |
| `python merge_pdfs.py -i DIR -o DIR` | Custom input / output folders |
| `python compress_pdfs.py` | Shrink each file to 2 MB into `compressed\` |
| `python compress_pdfs.py --preview` | Show sizes, write nothing |
| `python compress_pdfs.py --max-mb N` | Use a different cap |
| `python compress_pdfs.py --force` | Shrink even files already under the cap |
| `python compress_pdfs.py -i DIR -o DIR` | Custom input / output folders |

---

## How merging actually groups files

For a file sitting in `to_merge` (not in a subfolder), the script strips a **trailing index** from the name, then groups files that share what is left.

These suffixes are treated as page/part numbers and removed:

- `_1`, `-2`, `.3`
- ` page 1`, `_page2`, `-pg3`, `_p04`
- ` part 2`, `_pt3`
- `(1)`, `[12]`
- `copy`, `vol` / `volume`, `ch` / `chapter`, `sec` / `section`, `no` / `num` / `number`, `#`

Examples of the same group:

- `Contract_John_1.pdf` and `Contract_John_2.pdf` → group `Contract_John`
- `relevés_de_notes_1.pdf` and `relevés_de_notes_2.pdf` → group `relevés_de_notes`
- `Scan_p03.pdf` and `Scan_p04.pdf` → group `Scan`

Order inside a group is **natural sort**, so:

`file_1.pdf`, `file_2.pdf`, `file_10.pdf`  
not  
`file_1.pdf`, `file_10.pdf`, `file_2.pdf`

A name with no trailing index (`Notes.pdf`) is its own group. If it is the only file in that group, it is copied rather than rewritten.

Subfolders skip this name logic. The folder name *is* the output name, and every PDF inside it is concatenated.

---

## How compression actually shrinks files

The compressor tries several strategies, **gentlest first**, and stops at the first result that is at most 2 MB. It never keeps a result larger than the original if the original was already under the limit.

1. **Copy** — file is already ≤ 2 MB.
2. **Lossless rewrite** — recompress PDF streams and drop duplicate objects. Text and images stay as they are.
3. **Ghostscript** — if Ghostscript is installed on the PC, use its `/ebook` then `/screen` quality presets. Optional; skipped if Ghostscript is not found.
4. **Image recompress** — downscale large embedded photos and re-save them as JPEG, stepping quality down until the file fits. Small icons (under 128 px) are left alone.
5. **Raster fallback** — render each page to a JPEG and build a new PDF. This almost always hits 2 MB, but the file becomes a stack of pictures (no selectable text). Used only if the steps above are not enough.
6. **Best effort** — if it still cannot fit, the smallest version is saved anyway and a warning is printed.

Methods you may see in the log: `copied`, `lossless`, `ghostscript`, `images`, `raster`, `best_effort`.

---

## Troubleshooting

**`python` is not recognized**  
Reinstall Python from python.org and tick **Add python.exe to PATH**. Close and reopen the terminal (or re-double-click the `.bat`).

**`No PDFs found`**  
The input folder has no `.pdf` files. Put files in `to_merge` or `to_compress`, not next to the scripts.

**Wrong files got merged together**  
Names were too similar after numbers were stripped. Put each document in its own subfolder instead, or preview first with `--preview`.

**Pages are in the wrong order**  
Rename with numeric prefixes: `01_intro.pdf`, `02_body.pdf`. Natural sort follows those numbers.

**A merged file was skipped / warning about password**  
That source PDF is encrypted. Remove the password in another tool, then drop it in again.

**Compressed file is blurry, or text cannot be selected**  
The log will say `raster` or “flattened to images”. The original was too large to fit as a normal PDF. Keep the original in `to_compress` if you still need a sharp copy, and use the compressed file only for upload limits.

**Still over 2 MB after compress**  
Rare (very many pages, or a damaged file). The log will say `best_effort`. Try `--max-mb 2` again, or split the document before compressing.

**Want a smaller cap than 2 MB**

```powershell
python compress_pdfs.py --max-mb 1
```

**Python packages missing** (`ModuleNotFoundError: pypdf` / `PIL` / `pypdfium2`)

```powershell
cd C:\Users\yahya\Desktop\pdf_kit
python -m pip install -r requirements.txt
```

---

## Tests

From the project folder:

```powershell
python tests/test_grouping.py
python tests/test_compress.py
```

These create temporary PDFs, run merge grouping and compression, then throw the temps away. They do not touch your `to_merge` or `to_compress` files.
