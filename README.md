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

**A note on the ESV API key:** decks don't ship with one. Open any generated deck, click the ⚙️ **Settings** button, and paste in your own free key from [api.esv.org/account](https://api.esv.org/account) — it's saved to that browser's local storage, never written into the file itself. Without a key, the Bible reader falls back to free public-domain translations (KJV, WEB, and others).

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

### Deploying to Render (free tier)

1. Push this repository to GitHub (see above).
2. Create a free account at [render.com](https://render.com) and connect your GitHub account.
3. **New → Web Service**, pick this repository.
4. Set:
   - **Root Directory**: `server`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: Free
5. Create the service. Render builds and deploys automatically, and redeploys on every push to your default branch.
6. Your app is live at the `https://<your-service>.onrender.com` URL Render gives you.

Notes: the free tier spins down after periods of inactivity (the first request after a while takes ~30–60s to wake it up), has limited memory (watch out with very large PDFs), and its filesystem is ephemeral — `server/generated/` output doesn't persist across restarts/redeploys, which is expected since it's meant to be downloaded immediately, not stored long-term.

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
