#!/usr/bin/env python3
"""
Bible Study Deck Generator — web server.

Hosts the original scripts/generate_deck.py (pymupdf-based parsing — handles
PDFs that break the browser-only version's PDF.js text extraction) behind a
small Flask upload form, so it can be used from any browser without
installing Python locally.

Run locally:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
"""
import re
import shutil
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, render_template, request, send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generate_deck as gd  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB


def build_file_base(deck_title: str) -> str:
    """Mirrors generate_deck.py main()'s <BOOK>_mmmYYYY output naming."""
    book_name = "study"
    if deck_title:
        m = re.search(r"\(([^)]+)\)", deck_title)
        if m:
            inner_clean = re.sub(r"[^a-zA-Z0-9]", "", m.group(1).strip()).lower()
            if inner_clean:
                book_name = inner_clean
        else:
            first_word = deck_title.split()[0]
            book_name = re.sub(r"[^a-zA-Z0-9]", "", first_word).lower()
    if not book_name or len(book_name) < 2:
        book_name = "study"
    month_abbr = datetime.now().strftime("%b").lower()
    year_4d = datetime.now().strftime("%Y")
    return f"{book_name}_{month_abbr}{year_4d}"


def summarize(studies: list) -> list:
    rows = []
    for i, s in enumerate(studies, 1):
        q = sum(1 for sl in s["slides"] if sl["type"] in ("question", "implications-questions"))
        c = sum(1 for sl in s["slides"] if sl["type"] == "commentary")
        r = sum(1 for sl in s["slides"] if sl["type"] == "bible-read")
        rows.append({"index": i, "title": s["title"], "count": len(s["slides"]), "c": c, "r": r, "q": q})
    return rows


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    file = request.files.get("pdf")
    if not file or not file.filename:
        return render_template("index.html", error="Please choose a PDF file."), 400
    if not file.filename.lower().endswith(".pdf"):
        return render_template("index.html", error="Please choose a PDF file (.pdf)."), 400

    token = uuid.uuid4().hex[:12]
    work_dir = GENERATED_DIR / token
    work_dir.mkdir(parents=True)
    pdf_path = work_dir / file.filename
    file.save(str(pdf_path))

    try:
        text = gd.extract_text_from_pdf(str(pdf_path))
        if not text.strip():
            raise ValueError("No text extracted. The file may be scanned/image-only.")

        deck_title = gd._extract_deck_title(text)
        studies = gd.parse_studies(text)
        if not studies:
            raise ValueError(
                "No studies found. Check that the PDF uses the expected section "
                "headers (Getting Started / Observation & Interpretation / "
                "Implications & Obedience)."
            )

        file_base = build_file_base(deck_title)
        output_html = work_dir / f"{file_base}.html"
        gd.generate_html(studies, str(output_html), deck_title=deck_title, original_pdf=str(pdf_path))

        pdf_copy = output_html.with_suffix(".pdf")
        zip_path = work_dir / f"{file_base}.zip"
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(str(output_html), output_html.name)
            if pdf_copy.exists():
                zf.write(str(pdf_copy), pdf_copy.name)

        summary_rows = summarize(studies)
        return render_template(
            "result.html",
            token=token,
            html_name=output_html.name,
            pdf_name=pdf_copy.name if pdf_copy.exists() else None,
            zip_name=zip_path.name,
            deck_title=deck_title,
            summary=summary_rows,
            total_slides=sum(r["count"] for r in summary_rows),
            total_questions=sum(r["q"] for r in summary_rows),
        )
    except Exception as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        return render_template("index.html", error=str(e)), 400


@app.route("/generated/<token>/<path:filename>")
def generated_file(token, filename):
    d = GENERATED_DIR / token
    if not d.is_dir():
        abort(404)
    return send_from_directory(str(d), filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
