# Bible Study Deck Generator

Turns a Bible-study-guide PDF into a self-contained, presentable HTML deck (`templates/presentation.html`'s UI: keyboard-driven navigation, Bible verse reader, leader notes, dark/light themes, and more).

Version 1.0.0 · [MIT License](LICENSE)

There are three ways to generate a deck from a PDF — pick whichever suits you.

## Option A — Web app (no installation)

Open `docs/index.html` in a browser (or the GitHub Pages URL once this repo is published — see below), drop in a PDF, and download the generated deck. Parsing runs entirely in your browser; nothing is uploaded anywhere.

The web app is a JavaScript port of the same parsing logic as the Python script below, tuned to match its output closely.

**Important:** after downloading, save both the `.html` deck and the `.pdf` into the **same folder** with the filenames the app gives you — the deck's "Open original PDF" button only appears when the two files sit together with matching names.

**A known limitation:** some PDFs (often ones exported from tools like Canva or Pages) embed fonts without a proper character-ligature mapping. In the browser, this can make text extraction garble letter sequences like "ti"/"tt"/"ft" (e.g. "Getting" reads as "GeUng"), which breaks the web app's section-header detection — it'll show an error telling you as much rather than produce a broken deck. The Python CLI below handles these PDFs correctly (via `pymupdf`, which recovers the text more robustly), so use that for any PDF the web app rejects.

### Publishing the web app on GitHub Pages

1. Push this repository to GitHub.
2. In the repo, go to **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Pick your default branch and the **`/docs`** folder, then save.
5. GitHub will publish the site at `https://<you>.github.io/<repo>/` within a minute or two.

**A note on the ESV API key:** `templates/presentation.html` (and its copy at `docs/presentation-template.html`) has an ESV Bible API key hardcoded in it for the in-app Bible reader. GitHub Pages repos are public by default, so once you push, that key becomes visible to anyone who views the page source or browses the repo. If that's not something you want publicly exposed, either keep this repository private, or remove/replace the key (`ESV_API_KEY` near the top of the app script in `presentation.html`) before publishing — the reader falls back to other translations without it.

## Option B — Python command line

```bash
python3 scripts/generate_deck.py /path/to/your/study-guide.pdf
```

Requires `pymupdf` (`pip install pymupdf`). Generates the deck into `~/bible-study-decks/`, copies the PDF alongside it, and prints a summary of studies/slides/questions found.

## Option C — Server-hosted web app (handles any PDF the CLI handles)

A small Flask server in `server/` wraps the *original* `scripts/generate_deck.py` behind an upload form, so you get the CLI's accurate `pymupdf`-based parsing (no browser font-extraction limitations) through a normal web page. Use this for PDFs the client-side web app (Option A) rejects.

```bash
cd server
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000`, upload a PDF, and download the generated deck (or view the live preview on the result page). Each upload gets its own folder under `server/generated/` (not committed to git — see `server/.gitignore`); clean that folder out periodically since nothing deletes old runs automatically.

This needs a real Python host to put it on the web (GitHub Pages only serves static files) — any host that runs a Flask app works (Render, Railway, PythonAnywhere, Fly.io, a VPS, etc.). The steps above are for running it locally.

## Project layout

```
scripts/generate_deck.py       — Python CLI (PDF → deck, via pymupdf)
templates/presentation.html    — the deck viewer/presenter app
docs/                          — the client-side web app (GitHub Pages serves this folder)
  index.html, style.css        — upload UI
  parser.js                    — JS port of the Python parsing logic
  pdf-extract.js                — PDF.js text extraction tuned to match pymupdf's output
  app.js                        — wires upload → parse → preview → download
  presentation-template.html   — copy of templates/presentation.html
  pdf.min.js, pdf.worker.min.js — vendored PDF.js (no CDN dependency)
server/                        — the server-hosted web app (wraps scripts/generate_deck.py)
  app.py                       — Flask app: upload → parse_studies → generate_html → download/preview
  templates/, static/          — upload form and result page
  generated/                   — per-upload output (gitignored)
```
