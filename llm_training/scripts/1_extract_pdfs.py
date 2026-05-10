"""
Step 1 – Extract text from PDF books.

Usage:
    python llm_training/scripts/1_extract_pdfs.py

Place your PDF books in:  C:/Markets/
Output goes to:           llm_training/data/processed/book_chunks.jsonl

Each line in the output JSONL is:
    {"source": "book_name.pdf", "page": 3, "text": "...chunk text..."}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import fitz  # PyMuPDF

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parents[2]
BOOKS_DIR = Path(r"C:\Markets")
OUT_DIR = ROOT / "llm_training" / "data" / "processed"
OUT_FILE = OUT_DIR / "book_chunks.jsonl"

# Tuning
CHUNK_SIZE = 800       # target characters per chunk
CHUNK_OVERLAP = 100    # overlap to preserve context across chunk boundaries
MIN_CHUNK_LEN = 200    # discard chunks shorter than this (headers, footers, etc.)


# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(raw: str) -> str:
    """Remove noise: excessive whitespace, page numbers, footers."""
    # Normalise line endings
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Remove lone page numbers (a line that is just digits)
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)
    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace non-breaking spaces and weird unicode spaces
    text = re.sub(r"[\xa0\u200b\u200c\u200d\ufeff]", " ", text)
    # Collapse multiple spaces within a line
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ── Chunking ──────────────────────────────────────────────────────────────────

def split_into_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks at sentence/paragraph boundaries."""
    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + size, length)

        # Prefer to end at a sentence boundary (. ! ?)
        if end < length:
            boundary = max(
                text.rfind(". ", start, end),
                text.rfind(".\n", start, end),
                text.rfind("? ", start, end),
                text.rfind("! ", start, end),
            )
            if boundary != -1 and boundary > start + size // 2:
                end = boundary + 1

        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_LEN:
            chunks.append(chunk)

        start = end - overlap if end < length else length

    return chunks


# ── PDF processing ────────────────────────────────────────────────────────────

def extract_pdf(path: Path) -> list[dict]:
    """Extract and chunk all text from a single PDF."""
    records: list[dict] = []
    doc = fitz.open(str(path))
    full_pages: list[tuple[int, str]] = []

    for page_num, page in enumerate(doc, start=1):
        raw = page.get_text("text")
        cleaned = clean_text(raw)
        if len(cleaned) >= MIN_CHUNK_LEN:
            full_pages.append((page_num, cleaned))

    # Combine consecutive pages into larger text blocks, then chunk
    combined_text = "\n\n".join(t for _, t in full_pages)
    chunks = split_into_chunks(combined_text)

    for i, chunk in enumerate(chunks):
        records.append({
            "source": path.name,
            "chunk_id": i,
            "text": chunk,
        })

    doc.close()
    return records


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)  # creates C:\Markets if not present
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Recursively find all PDFs in C:\Markets and all sub-folders
    pdfs = sorted(BOOKS_DIR.rglob("*.pdf"))
    if not pdfs:
        print(f"[!] No PDF files found in {BOOKS_DIR} (searched recursively)")
        print("    Place your trading/finance books there and re-run.")
        return
    print(f"Found {len(pdfs)} PDF(s) across all sub-folders.")

    all_records: list[dict] = []
    for pdf_path in pdfs:
        # Show relative path so sub-folder is visible in output
        rel = pdf_path.relative_to(BOOKS_DIR)
        print(f"  Extracting: {rel} ...", end=" ", flush=True)
        records = extract_pdf(pdf_path)
        # Tag chunks with relative path (folder/book.pdf)
        for rec in records:
            rec["source"] = str(rel)
        all_records.extend(records)
        print(f"{len(records)} chunks")

    with OUT_FILE.open("w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nDone. {len(all_records)} total chunks → {OUT_FILE}")


if __name__ == "__main__":
    main()
