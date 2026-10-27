#!/usr/bin/env python3
"""
Bible Study Deck Generator
Version 1.0.0 — MIT License (see LICENSE)

Usage:
  python3 generate_deck.py /path/to/pdf/file.pdf

This script:
1. Extracts text from a local PDF file using pymupdf
2. Parses the text into studies with sections: Getting Started,
   Observation & Interpretation, Implications & Obedience
3. Generates a data JSON (var DECK_DATA = [...]) embedded in an HTML
   presentation template

Dependencies:
  - pymupdf (for PDF parsing):  uv pip install pymupdf
"""

__version__ = "1.0.0"

import re
import sys
from datetime import datetime
import json
import os
from pathlib import Path

import shutil

# ── Configuration ──────────────────────────────────────────────────
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "presentation.html"
OUTPUT_DIR = Path.home() / "bible-study-decks"

# ── Section header patterns ────────────────────────────────────────
SECTION_HEADERS = {
    "welcome": "Welcome",
    "getting_started": "Getting Started",
    "observation": r"Observation\s*(?:&|and)\s*Interpretation",
    "implications": r"Implications?\s*(?:&|and)\s*Obedience",
    "following_jesus": r"Following Jesus\s*:\s*Daily Discipleship in Life",
}

SIDEBAR_DELIM = r"——{3,}"  # 3 or more em-dashes / hyphens

# ── Known Bible book names (for reference expansion) ──────────────
KNOWN_BOOKS = {
    # Full names
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "Samuel", "Kings", "Chronicles",
    "Ezra", "Nehemiah", "Esther", "Job", "Psalms", "Psalm",
    "Proverbs", "Ecclesiastes", "Song", "Isaiah", "Jeremiah",
    "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "Corinthians", "Galatians", "Ephesians", "Philippians",
    "Colossians", "Thessalonians", "Timothy", "Titus", "Philemon",
    "Hebrews", "James", "Peter", "Jude", "Revelation",
    # Standard abbreviations
    "Gen", "Ex", "Lev", "Num", "Deut",
    "Josh", "Judg", "Ruth", "Sam", "Kgs", "Chr",
    "Ezr", "Neh", "Est", "Job", "Ps", "Prov", "Eccl",
    "Song", "Isa", "Jer", "Lam", "Ezek", "Dan", "Hos",
    "Joel", "Amos", "Obad", "Jon", "Mic", "Nah", "Hab",
    "Zeph", "Hag", "Zech", "Mal",
    "Matt", "Mk", "Lk", "Jn", "Acts",
    "Rom", "Cor", "Gal", "Eph", "Phil", "Col",
    "Thess", "Tim", "Tit", "Philem", "Heb", "Jas", "Pet",
    "Rev",
}
# Add lowercase versions (iterate over a copy)
for b in list(KNOWN_BOOKS):
    KNOWN_BOOKS.add(b.lower())
# Add dotted versions (e.g. "Cor.")
for b in list(KNOWN_BOOKS):
    if b.isalpha() and len(b) > 1:
        KNOWN_BOOKS.add(b + ".")
        KNOWN_BOOKS.add((b + ".").lower())

# Non-book words that commonly precede chapter:verse references
NON_BOOK_PREFIXES = {"cf", "cf.", "e.g", "e.g.", "i.e", "i.e.", "see", "v", "vv", "v.", "vv."}
NON_BOOK_PREFIXES.update(p.lower() for p in NON_BOOK_PREFIXES)


# ── Step 1: Extract text from PDF ──────────────────────────────────
def extract_text_from_pdf(path: str) -> str:
    """Extract text from a PDF using pymupdf."""
    try:
        import fitz
    except ImportError:
        raise ImportError("pymupdf not installed. Run: uv pip install pymupdf")

    doc = fitz.open(path)
    text = ""
    for page in doc:
        page_text = page.get_text()
        if page_text.strip():
            text += page_text + "\n"
    doc.close()
    return text


# ── Step 2: Parse text into studies ────────────────────────────────
def parse_studies(text: str) -> list:
    """Parse raw text into a list of studies.

    Each study: {
        "title": str,
        "slides": [{"type": str, "section": str, "content": str, ...}, ...]
    }
    """
    text = text.strip()
    if not text:
        return []

    studies = []
    study_pattern = r'(?m)^(?:Study|Lesson|Session)\s+(\d+)[:\s\.\-–—]*\s*(.*?)$'

    all_matches = []
    for m in re.finditer(study_pattern, text, re.IGNORECASE):
        line_no = text[: m.start()].count("\n")
        all_matches.append((line_no, m))

    if not all_matches:
        slides = _parse_q_and_a_section(text, "Observation & Interpretation")
        studies.append({"title": "Study", "slides": slides})
        return studies

    # Filter out TOC entries (those clustered near the top)
    if len(all_matches) >= 3:
        toc_cluster_end = 0
        for line_no, _ in all_matches:
            if line_no < 500:
                toc_cluster_end = line_no
            else:
                break
        has_content_cluster = any(
            line_no > toc_cluster_end + 50 for line_no, _ in all_matches
        )
        if toc_cluster_end > 0 and has_content_cluster:
            content_start_idx = next(
                i
                for i, (line_no, _) in enumerate(all_matches)
                if line_no > toc_cluster_end + 50
            )
            all_matches = all_matches[content_start_idx:]

    matches = [m for _, m in all_matches]

    for i, m in enumerate(matches):
        study_num = m.group(1)
        study_title_line = m.group(2).strip()
        study_start = m.end()
        study_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        study_body = text[study_start:study_end].strip()

        title_parts = [f"Study {study_num}"]
        if study_title_line:
            title_parts.append(study_title_line)
        title = ": ".join(title_parts)

        # Extract study date from the first line(s) of the study body
        # Typically like "Week Of June 28 - July 4" right after the title
        study_date = _extract_study_date(study_body)

        slides = parse_slides_from_study(study_body)
        studies.append({"title": title, "date": study_date, "slides": slides})

    return studies


# ── Step 3: Parse a single study into slides ────────────────────────
def parse_slides_from_study(text: str) -> list:
    """Parse a study body into slides with section-aware processing."""
    slides = []

    # 1. Find section boundaries
    sections = _split_into_sections(text)
    if not sections:
        return slides

    # 2. Process each section in order
    for section_name, section_text in sections:
        if section_name in ("following_jesus", "welcome"):
            # Skip Following Jesus and Welcome sections entirely
            continue
        slides += _process_section(section_name, section_text)

    return slides


def _split_into_sections(text: str) -> list:
    """Split study text into ordered sections. Returns [(name, text), ...].

    Only sections that appear AFTER the study title are considered — skips
    stray header words that appear in the TOC or other non-study areas.
    """
    # First find the study header to anchor our search
    study_match = re.search(r"(?mi)^(?:Study|Lesson|Session)\s+\d+", text)
    search_anchor = study_match.start() if study_match else 0

    text_after_study = text[search_anchor:]

    # Build a regex for all section headers
    section_patterns = []
    for key, pattern in SECTION_HEADERS.items():
        section_patterns.append((key, re.compile(pattern, re.IGNORECASE)))

    # Find all section header positions relative to the study text only
    found = []
    for key, pat in section_patterns:
        for m in pat.finditer(text_after_study):
            # Only accept section headers that are on their own line
            # (preceded by newline or at start of string)
            line_start = m.start()
            is_own_line = (
                line_start == 0 or text_after_study[line_start - 1] == "\n"
            )
            if not is_own_line:
                continue
            found.append((m.start() + search_anchor, key, m.end() + search_anchor))

    if not found:
        return []

    # Sort by position
    found.sort(key=lambda x: x[0])

    # Build sections: from each header to the next header
    sections = []
    for i, (start, key, header_end) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        # The section text starts after the header line itself
        header_line_end = text.find("\n", header_end)
        if header_line_end == -1:
            header_line_end = header_end
        section_text = text[header_line_end:end].strip()
        sections.append((key, section_text))

    return sections


def _process_section(section_name: str, text: str) -> list:
    """Process a section's text into slides."""
    slides = []

    if not text.strip():
        return slides

    # Display name for the section
    display_name = {
        "getting_started": "Getting Started",
        "observation": "Observation & Interpretation",
        "implications": "Implications & Obedience",
    }.get(section_name, section_name.replace("_", " ").title())

    if section_name == "getting_started":
        # Getting Started: all text is commentary — skip section header slide
        paras = _split_paragraphs(text)
        if paras:
            html = "".join(f"<p>{p}</p>" for p in paras)
            slides.append({
                "type": "commentary",
                "section": display_name,
                "content": html
            })
        return slides

    if section_name == "observation":
        # Parse the section — skip section header slide
        slides += _parse_q_and_a_section(text, section_name=display_name)
        return slides

    if section_name == "implications":
        raw_slides = _parse_q_and_a_section(text, section_name=display_name)

        # Separate questions from other slides
        questions = [s for s in raw_slides if s["type"] == "question"]
        other_slides = [s for s in raw_slides if s["type"] != "question"]

        # Filter out non-question content that's just instructional text
        filtered_others = []
        for s in other_slides:
            content = s.get("content", "")
            # Skip slides that are just instructions like "(Choose one or more...)"
            if content.strip().startswith("(Choose") or content.strip().startswith("(Pick"):
                continue
            filtered_others.append(s)

        # Add non-question slides FIRST (commentary, sidebars, bible-reads)
        slides += filtered_others

        # Then combine all questions into ONE slide as tiles
        if questions:
            q_html_parts = []
            for q in questions:
                content = q["content"]
                q_html_parts.append(f'<div class="implications-question">{content}</div>')
            combined_content = "".join(q_html_parts)
            slides.append({
                "type": "implications-questions",
                "section": display_name,
                "content": combined_content,
            })

        return slides

    return slides


def _strip_footnotes_from_question(text: str) -> str:
    """Strip trailing footnote numbers from question text.

    Removes patterns like ' 1 16', ' 5 18', ' 4', etc. at the end of text
    that are clearly footnote references, not part of the actual question.
    Also handles ' 1\\n16' (footnotes on separate lines that got joined).
    """
    # First normalize: strip trailing whitespace, handle footnotes joined via newline
    text = re.sub(r'\s+', ' ', text).strip()
    # Strip trailing standalone numbers (1-2 groups of 1-3 digits)
    text = re.sub(r'\s+\d{1,3}(?:\s+\d{1,3})?\s*$', '', text)
    return text.strip()


# ── Bible Context Tracking & Reference Expansion ──────────────────

def _parse_passage_context(passage: str) -> tuple:
    """Extract (book_name, default_chapter) from a passage reference.

    '1 Corinthians 1:1-31' → ('1 Corinthians', 1)
    '1 Corinthians 3:1-4:7' → ('1 Corinthians', 3)
    '1 Corinthians 10:14-11:1' → ('1 Corinthians', 10)
    '1 Corinthians 1:1-2:16' → ('1 Corinthians', 1)
    Returns (None, None) if parsing fails.
    """
    # Match: optional number prefix, book name, then chapter:verse
    m = re.match(
        r'^((?:\d\s+)?[A-Za-z][A-Za-z\s]+?)\s+(\d+):',
        passage.strip()
    )
    if m:
        book = m.group(1).strip()
        # Normalize: remove trailing period
        if book.endswith('.'):
            book = book[:-1]
        chapter = int(m.group(2))
        return (book, chapter)
    return (None, None)


def _is_preceded_by_book(text: str, pos: int) -> bool:
    """Check if the text at position `pos` is preceded by a known book name."""
    before = text[max(0, pos - 50):pos].strip()
    # Get the last few words
    words = re.findall(r"[A-Za-z]+\.?", before)
    if not words:
        return False

    # Check the last word
    last = words[-1].lower()
    if last in KNOWN_BOOKS:
        return True

    # Check if last two words form a numbered book (e.g., "1 Corinthians")
    if len(words) >= 2:
        last_two = words[-2].lower() + " " + words[-1].lower()
        # Check if this matches any known book with a number prefix
        for book in ("1 corinthians", "2 corinthians", "1 samuel", "2 samuel",
                     "1 kings", "2 kings", "1 chronicles", "2 chronicles",
                     "1 peter", "2 peter", "1 john", "2 john", "3 john",
                     "1 thessalonians", "2 thessalonians", "1 timothy", "2 timothy",
                     "1 cor", "2 cor", "1 sam", "2 sam", "1 kgs", "2 kgs",
                     "1 chr", "2 chr", "1 pet", "2 pet", "1 jn", "2 jn", "3 jn",
                     "1 thess", "2 thess", "1 tim", "2 tim",
                     "1 Corinthians", "2 Corinthians",
                     "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
                     "1 Chronicles", "2 Chronicles", "1 Peter", "2 Peter",
                     "1 John", "1 Thessalonians", "2 Thessalonians",
                     "1 Timothy", "2 Timothy"):
            if last_two.startswith(book.lower()):
                return True

    # Check if preceded by a non-book prefix (cf., e.g., see) - these are NOT book names
    if last.lower() in NON_BOOK_PREFIXES:
        return False

    # Check if the last word looks like a book name (capitalized, starts with uppercase)
    # This catches refs like "Luke 22:14-20" but not "context 3:7"
    if words[-1][0].isupper() and len(words[-1]) > 1:
        return True

    return False


def _expand_question_refs(text: str, book: str, chapter: int) -> str:
    """Expand short Bible references in question text using context.

    Steps:
    1. Expand bare verse references (v 26 → 1 Corinthians 1:26)
    2. Expand short chapter:verse refs (3:7 → 1 Corinthians 3:7)
    3. Wrap all expanded refs in bible-ref tags
    """
    if not book:
        return text

    # ── Step 1: Expand bare verse references ──
    # Pattern: "v 26", "vv 2, 4-9, 30-31", "v. 26", "vv. 2-7"
    def _expand_verse_list(m):
        prefix = m.group(1)  # v, vv, v., vv.
        refs = m.group(2).strip()  # the verse numbers
        # Split by semicolons first to preserve paragraph-like structure
        segments = re.split(r'(;)', refs)
        result_parts = []
        for seg in segments:
            if seg == ';':
                result_parts.append('; ')
                continue
            if not seg.strip():
                continue
            # Split segment by commas
            parts = [p.strip() for p in seg.split(',') if p.strip()]
            expanded_parts = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # Remove leading 'v ' or 'vv ' if present
                part = re.sub(r'^[vV]\.?\s*', '', part)
                if not part:
                    continue
                # Check if this part already has a chapter:verse format
                if re.match(r'^\d+:\d', part):
                    expanded_parts.append(f"{book} {part}")
                else:
                    expanded_parts.append(f"{book} {chapter}:{part}")
            result_parts.append(", ".join(expanded_parts))
        return "".join(result_parts)

    text = re.sub(
        r'\b([vV]\.?|[vV][vV]\.?)\s+([\d,\s\-;:]+)',
        _expand_verse_list,
        text
    )

    # ── Step 2: Expand short chapter:verse refs without book prefixes ──
    # Process character by character to handle overlapping replacements
    result = ""
    i = 0
    while i < len(text):
        # Look for chapter:verse patterns
        m = re.search(r'(\d+):(\d+(?:-\d+)?)', text[i:])
        if not m:
            # No more matches — handled by the post-loop append below
            break

        abs_start = i + m.start()
        abs_end = i + m.end()

        # Copy text before this match
        result += text[i:abs_start]

        # Check if preceded by a book name
        if not _is_preceded_by_book(text, abs_start):
            # This is a short ref - expand it
            full_ref = f"{book} {m.group(1)}:{m.group(2)}"
            result += full_ref
        else:
            # Already has book prefix, keep as-is
            result += text[abs_start:abs_end]

        i = abs_end

    # Add any remaining text after the last match
    result += text[i:]
    text = result

    # ── Step 3: Handle ":-" pattern (missing start verse, e.g. "2:-24" → "2:1-24") ──
    text = re.sub(r':-(\d+)', r':1-\1', text)

    # ── Step 4: Wrap expanded refs in bible-ref tags ──
    text = _link_bible_refs(text)

    # ── Step 5: Link comma-separated verse continuations ──
    text = _link_comma_continuations(text)

    return text


def _link_bible_refs(text: str) -> str:
    """Convert Bible references in text to hyperlinks with bible-ref class.

    Handles expanded references like '1 Corinthians 3:7' and also
    captures optional trailing letter suffix (e.g. '1:5a') — the letter
    is included in display text but stripped from data-ref.
    """
    # Match full book+chapter:verse references
    # Pattern: (optional number) BookName chapter:verse[optional letter suffix]
    pattern = r'\b((?:\d\s+)?[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(\d+:\d+(?:-\d+)?)([a-z])?\b'

    def _replace_ref(m):
        # Plain text output — no hover tooltip, just the reference
        book = m.group(1)
        ref = m.group(2)
        suffix = m.group(3) or ''
        display = f"{book} {ref}{suffix}".strip()
        # No anchor tag — just display the reference as plain text
        return display

    text = re.sub(pattern, _replace_ref, text)
    return text


def _link_comma_continuations(text: str) -> str:
    """Second pass to link comma-separated verse continuations.

    After a bible-ref closing tag, looks for patterns like ', 4' or ', 4-6'
    and creates new bible-ref elements using the same book and chapter
    from the preceding reference.

    Example:
        '<a ...>1 Corinthians 2:1</a>, 4' →
        '<a ...>1 Corinthians 2:1</a>, <a ... data-ref="1 Corinthians 2:4">4</a>'
    """
    def _replace_verse(m):
        verses = m.group(1)
        # Find the last bible-ref data-ref before this match
        match_start = m.start()
        pre_text = text[:match_start]
        last_refs = re.findall(r'data-ref="([^"]+)"', pre_text)
        if last_refs:
            data_ref = last_refs[-1]
            last_colon = data_ref.rfind(':')
            if last_colon != -1:
                base = data_ref[:last_colon + 1]
                new_ref = f"{base}{verses}"
                return (
                    f'</a>, <a href="#" class="bible-ref" '
                    f'data-ref="{new_ref}">{verses}</a>'
                )
        return m.group(0)

    # Loop to handle multiple continuations after the same ref
    # (e.g. '1 Cor 2:1</a>, 4, 5, 6' — each iteration links the next one)
    while True:
        new_text = re.sub(r'</a>,\s*(\d+(?:-\d+)?)', _replace_verse, text)
        if new_text == text:
            break
        text = new_text
    return text


# ── Parse Q&A sections with context tracking ──────────────────────

def _parse_q_and_a_section(text: str, section_name: str = "Observation & Interpretation") -> list:
    """Parse a section that may contain questions, Read-lines, commentary, and sidebars.

    Line-by-line parser that handles:
    - Multi-line question text (continuation lines joined to the question)
    - Sidebars delimited by em-dash/hyphen lines
    - SIDEBAR N: headers
    - "Read ..." passage references
    - Context-aware Bible reference expansion

    Each slide gets a "section" field set to section_name.
    """
    slides = []
    lines = text.split("\n")

    # Bible context tracking
    context_book = None
    context_chapter = None

    def make_slide(slide_type, content, extra=None):
        """Create a slide dict with section metadata."""
        slide = {"type": slide_type, "section": section_name, "content": content}
        if extra:
            slide.update(extra)
        return slide

    buf = []  # commentary buffer

    def flush_commentary():
        nonlocal buf
        if not buf:
            return
        body = " ".join(line.strip() for line in buf if line.strip()).strip()
        if body:
            # Strip footnote markers
            body = re.sub(r"\b\d{1,3}\b(?![:.)])", "", body)  # standalone numbers (non-verse)
            body = re.sub(r"\s{2,}", " ", body).strip()
            paras = _split_paragraphs(body)
            html = "".join(f"<p>{p}</p>" for p in paras)
            # Convert Bible references to hyperlinks
            html = _link_bible_refs(html)
            slides.append(make_slide("commentary", html))
        buf = []

    # Sidebar state machine
    in_sidebar = False
    sidebar_lines = []

    def flush_sidebar():
        nonlocal in_sidebar, sidebar_lines
        if not sidebar_lines:
            return
        # Extract sidebar title
        sidebar_title = ""
        cleaned = []
        for sl in sidebar_lines:
            m = re.match(r"^SIDEBAR\s+(\d+)\s*:\s*(.*)", sl, re.IGNORECASE)
            if m and not sidebar_title:
                sidebar_title = m.group(2).strip()
            if not re.match(r"^SIDEBAR\s+\d+\s*:", sl, re.IGNORECASE):
                cleaned.append(sl)
        body = " ".join(cleaned).strip()
        if body:
            label = f"[Sidebar \u2014 {sidebar_title}]" if sidebar_title else "[Sidebar content]"
            slides.append(make_slide("commentary", f"<p><em>{label}</em></p><p>{body}</p>"))
        sidebar_lines = []
        in_sidebar = False

    sidebar_delim = re.compile(r"^——{2,}—*$|^—{3,}$|^-{3,}$")

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        # ── Handle sidebar state ──
        if sidebar_delim.match(line):
            if in_sidebar:
                flush_sidebar()
            # When NOT in sidebar, a delimiter line starts a new sidebar
            # (but only if the next non-empty line looks like a sidebar header)
            else:
                flush_commentary()
                # Look ahead a few lines to check if this is actually a sidebar
                lookahead = ''.join(lines[i:i+5])
                if re.search(r'SIDEBAR\s+\d+\s*:', lookahead, re.IGNORECASE):
                    in_sidebar = True
                else:
                    # Not a sidebar — treat the delimiter as a separator and skip
                    i += 1
                    continue
            i += 1
            continue

        if in_sidebar:
            if line:
                sidebar_lines.append(line)
            i += 1
            continue

        # ── Skip empty lines ──
        if not line:
            i += 1
            continue

        # ── "Read ..." line — update Bible context ──
        read_match = re.match(r"^Read\s+(.+?)(?:\s*\.\s*)?$", line)
        if read_match:
            flush_commentary()
            passage = read_match.group(1).strip().lstrip()

            # Update Bible context
            parsed_book, parsed_chapter = _parse_passage_context(passage)
            if parsed_book:
                context_book = parsed_book
                context_chapter = parsed_chapter

            slides.append(make_slide(
                "bible-read",
                f"Read {passage}",
                {"passage": passage}
            ))
            i += 1
            continue

        # ── Numbered question ──
        q_match = re.match(r"^(\d+)[\.\)]\s", line)
        if q_match:
            q_num = int(q_match.group(1))
            # Ignore footnote-level numbers (footnotes are typically > 50)
            if q_num > 50:
                buf.append(raw)
                i += 1
                continue

            flush_commentary()

            # Collect question text, including continuation lines
            rest = line[len(q_match.group(0)):]
            q_text = f"{q_num}. {rest}"

            i += 1
            while i < len(lines):
                next_raw = lines[i]
                next_line = next_raw.strip()
                # Stop if blank line
                if not next_line:
                    break
                # Stop if sidebar delimiter
                if sidebar_delim.match(next_line):
                    break
                # Stop if SIDEBAR header
                if re.match(r"^SIDEBAR\s+\d+\s*:", next_line, re.IGNORECASE):
                    break
                # Stop if next "Read" line
                if re.match(r"^Read\s+", next_line):
                    break
                # Stop if next numbered question
                if re.match(r"^\d+[\.\)]\s", next_line):
                    break
                q_text += " " + next_line
                i += 1

            q_text = re.sub(r"\s+", " ", q_text).strip()
            # Strip trailing footnote numbers from question text
            q_text = _strip_footnotes_from_question(q_text)
            # Expand short Bible references using context
            q_text = _expand_question_refs(q_text, context_book, context_chapter)
            slides.append(make_slide("question", q_text))
            continue

        # ── Regular commentary line ──
        buf.append(raw)
        i += 1

    flush_commentary()
    if in_sidebar:
        flush_sidebar()
    return slides


def _split_paragraphs(text: str) -> list:
    """Split text into paragraphs by double newlines, clean each."""
    if not text.strip():
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras if paras else [text]


def _extract_deck_title(text: str) -> str:
    """Extract the overall deck title from the first page of the PDF.

    The title is the first substantive block of text before the first
    'Study N:' header. It's usually on the first page underneath a graphic
    and may span multiple lines.
    Examples: 'Glorious Christ, Inglorious Church? (1 Corinthians: The Church in the City)'
    """
    # Find the first study header
    study_match = re.search(r"(?mi)^(?:Study|Lesson|Session)\s+\d+", text)
    if study_match:
        pre_text = text[: study_match.start()].strip()
        pre_lines = [l.strip() for l in pre_text.split("\n") if l.strip()]
        if len(pre_lines) > 20:
            pre_text = "\n".join(pre_lines[:20])
    else:
        pre_text = text[:3000]

    lines = [l.strip() for l in pre_text.split("\n") if l.strip()]
    copyright_markers = [
        "©", "copyright", "all rights reserved", "no part",
        "this publication", "these studies are adapted", "scripture quotations",
        "this resource was downloaded", "permission", "arpc@", "website:",
    ]
    title_lines = []
    seen_title_start = False

    for line in lines:
        if len(line) < 5:
            continue
        line_lower = line.lower()
        is_copyright = False
        for marker in copyright_markers:
            if marker in line_lower:
                is_copyright = True
                break
        if is_copyright:
            break

        if line.isupper() and len(line) > 10:
            if seen_title_start:
                break
            continue

        if re.match(r"^[A-Z][a-z]+\s*[-–—]\s*[A-Z][a-z]+\s+\d{4}", line):
            break
        if re.match(r"^\d{4}$", line):
            break

        seen_title_start = True
        title_lines.append(line)

        if line.count("(") == line.count(")") and line.count(")") > 0 and line.endswith(")"):
            break

    if title_lines:
        title = " ".join(title_lines)
        title = re.sub(r"\s+", " ", title).strip().rstrip(".")
        title = re.sub(r"\s+\d{4}\s*$", "", title).strip()
        title = re.sub(r"\s+[A-Z][a-z]+\s*-\s*[A-Z][a-z]+\s+\d{4}\s*$", "", title).strip()
        if title:
            return title
    return "Bible Study"


def _extract_study_date(text: str) -> str:
    """Extract a date range from the first lines of a study body.

    Looks for patterns like 'Week Of June 28 - July 4' or 'Week Of July 5-11'
    right after the study title heading. Returns empty string if no date found.
    """
    first_line = text.split("\n")[0].strip() if text else ""
    # Pattern: optional "Week Of" + Month Day - Month Day (or Month Day-Day)
    m = re.match(
        r"^(?:Week\s+Of\s+)?([A-Z][a-z]+ \d+)\s*[-–—]\s*(?:([A-Z][a-z]+) )?(\d+)",
        first_line
    )
    if m:
        month1_day = m.group(1)  # e.g. "June 28"
        month2 = m.group(2)      # e.g. "July" or None
        day2 = m.group(3)        # e.g. "4" or "11"
        if month2:
            return f"Week Of {month1_day} — {month2} {day2}"
        else:
            # Same month inferred
            month1 = month1_day.split()[0]
            return f"Week Of {month1} {month1_day.split()[1]} — {day2}"
    # Try just a single date
    m = re.match(r"^(?:Week\s+Of\s+)?([A-Z][a-z]+ \d+)$", first_line)
    if m:
        return m.group(1)

    # Edge case: title wraps across lines, date is on line 1 or 2
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for candidate in lines[1:4]:  # Check lines 1-3 for date
        m = re.match(r"^(?:Week\s+Of\s+)?([A-Z][a-z]+ \d+)\s*[-–—]\s*(?:([A-Z][a-z]+) )?(\d+)", candidate)
        if m:
            month1_day = m.group(1)
            month2 = m.group(2)
            day2 = m.group(3)
            if month2:
                return f"Week Of {month1_day} — {month2} {day2}"
            else:
                month1 = month1_day.split()[0]
                return f"Week Of {month1} {month1_day.split()[1]} — {day2}"
        m = re.match(r"^(?:Week\s+Of\s+)?([A-Z][a-z]+ \d+)$", candidate)
        if m:
            return m.group(1)

    return ""


# ── Step 4: Generate HTML ──────────────────────────────────────────
def generate_html(studies: list, output_path: str, deck_title: str = "📖 Bible Study", original_pdf: str = ""):
    """Generate the HTML deck from parsed studies.

    Injects the study data as a JavaScript `var DECK_DATA = [...]` variable
    and the deck title as `var DECK_TITLE = "..."`.
    """
    template_file = TEMPLATE_PATH
    if not template_file.exists():
        template_file = (
            Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
            / "skills"
            / "productivity"
            / "generate-bible-study-deck"
            / "templates"
            / "presentation.html"
        )

    if not template_file.exists():
        raise FileNotFoundError(
            f"Template not found at {TEMPLATE_PATH}. Ensure the skill is installed."
        )

    html = template_file.read_text(encoding="utf-8")
    data_json = json.dumps(studies, ensure_ascii=False, indent=2)

    # Inject DECK_TITLE and DECK_PDF_URL
    deck_title_clean = json.dumps(deck_title, ensure_ascii=False)

    # Build PDF URL — copy PDF alongside the HTML and use relative URL
    deck_pdf_url = ""
    if original_pdf and os.path.exists(original_pdf):
        pdf_dest = Path(output_path).with_suffix(".pdf")
        try:
            shutil.copy2(original_pdf, str(pdf_dest))
            deck_pdf_url = pdf_dest.name
        except (shutil.Error, OSError):
            deck_pdf_url = ""
    # After renaming to <BOOK>_mmmYYYY format, update URL if renamed PDF exists
    # pdf_new is set in main() after generate_html; the caller updates HTML, but since
    # generate_html writes to output_path, the HTML must reference the renamed PDF.
    # We set it based on what main() will rename to — derived from file_base.
    # (The simpler fix: main passes file_base to generate_html; for now we rely on
    # the post-rename copy in main() to sync, and manually patch DECK_DATA after rename.)
    pdf_url_clean = json.dumps(deck_pdf_url, ensure_ascii=False)

    deck_var_meta = f"<script>var DECK_TITLE = {deck_title_clean}; var DECK_PDF_URL = {pdf_url_clean};</script>\n"

    # Replace script tag (old format) with DECK_DATA variable
    deck_var_script = f"{deck_var_meta}<script>\nvar DECK_DATA = {data_json};\n</script>"

    # Try to replace the old deck-data script tag if present
    old_tag_pattern = r'<script id="deck-data" type="application/json">.*?</script>'
    if re.search(old_tag_pattern, html, flags=re.DOTALL):
        html = re.sub(
            old_tag_pattern,
            deck_var_script,
            html,
            flags=re.DOTALL,
        )
    else:
        # Inject before the first <script> in <body> (the app script)
        # so that DECK_DATA is available when loadData() runs
        first_script = html.find("<script>\n(function")
        if first_script == -1:
            first_script = html.find("<script>")
        if first_script != -1:
            html = html[:first_script] + deck_var_script + "\n" + html[first_script:]
        else:
            html = html.replace("</body>", f"{deck_var_script}\n</body>")

    study_count = len(studies)
    html = re.sub(
        r"<title>Bible Study Deck</title>",
        f"<title>Bible Study ({study_count} studies)</title>",
        html,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"✅ Deck generated: {output_path.resolve()}")


# ── Step 5: Main entry point ────────────────────────────────────────
def parse_pdf(pdf_path: str) -> list:
    """Parse a PDF file and return a list of study dicts.

    This is the main entry point for programmatic use.
    Each study has: {"title": str, "slides": [{"type": str, "section": str, "content": str}, ...]}
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise ValueError(
            "No text extracted. The file may be scanned/image-only."
        )

    print(f"📝 Extracted {len(text):,} characters")

    # ── Extract the deck title from the first page ──
    # The deck title is typically the first substantive line(s) on page 1,
    # before the first "Study N:" header. Usually appears under a graphic.
    deck_title = _extract_deck_title(text)
    print(f"📖 Deck title: {deck_title}")

    studies = parse_studies(text)

    total_slides = sum(len(s["slides"]) for s in studies)
    total_questions = sum(
        sum(1 for sl in s["slides"] if sl["type"] == "question") for s in studies
    )
    print(
        f"📚 Found {len(studies)} studies, {total_slides} slides ({total_questions} questions)"
    )

    return studies


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_deck.py /path/to/pdf/file.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]

    try:
        studies = parse_pdf(pdf_path)

        output_dir = OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract the deck title from the PDF text
        # Need to re-extract since parse_pdf returns studies but not the raw title
        text = extract_text_from_pdf(pdf_path)
        deck_title = _extract_deck_title(text)

        first_title = studies[0]["title"] if studies else "bible-study"
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", first_title.lower()).strip("-")[:40]
        if len(studies) > 1:
            slug = f"{slug}-and-{len(studies)-1}-more"
        output_path = output_dir / f"{slug}.html"

        generate_html(studies, str(output_path), deck_title=deck_title, original_pdf=os.path.abspath(pdf_path))
        
        # -- Naming: <BOOK>_mmmYYYY --
        book_name = "study"
        if deck_title:
            # Try "(Book)" or "(Book N)" inside parens first
            m = re.search(r"\(([^)]+)\)", deck_title)
            if m:
                inner = m.group(1).strip()
                # Keep the full inner text (e.g. "1 Chronicles" -> "1chronicles")
                inner_clean = re.sub(r"[^a-zA-Z0-9]", "", inner).lower()
                if inner_clean:
                    book_name = inner_clean
            else:
                # Fall back to first word of title
                first_word = deck_title.split()[0]
                book_name = re.sub(r"[^a-zA-Z0-9]", "", first_word).lower()
        if not book_name or len(book_name) < 2:
            book_name = "study"
        month_abbr = datetime.now().strftime("%b").lower()
        year_4d = datetime.now().strftime("%Y")
        file_base = f"{book_name}_{month_abbr}{year_4d}"
        out_dir = output_dir / file_base
        out_dir.mkdir(parents=True, exist_ok=True)
        html_new = out_dir / f"{file_base}.html"
        pdf_new = out_dir / f"{file_base}.pdf"
        import shutil, zipfile
        if output_path.exists():
            shutil.copy2(str(output_path), str(html_new))
        pdf_src = output_path.with_suffix(".pdf")
        if pdf_src.exists():
            shutil.copy2(str(pdf_src), str(pdf_new))
        zip_path = out_dir.parent / f"{file_base}.zip"
        with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in out_dir.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    zf.write(str(f), f.name)
        print(f"📦 ZIP: {zip_path}")
        output_path = html_new

        print(f"\n{'=' * 50}")
        print(f"📖 Bible Study Deck Summary")
        print(f"{'=' * 50}")
        for i, s in enumerate(studies, 1):
            q = sum(1 for sl in s["slides"] if sl["type"] in ("question", "implications-questions"))
            c = sum(1 for sl in s["slides"] if sl["type"] == "commentary")
            r = sum(1 for sl in s["slides"] if sl["type"] == "bible-read")
            print(
                f"  {i}. {s['title']} \u2014 {len(s['slides'])} slides ({c}C, {r}R, {q}Q)"
            )
        print(f"{'=' * 50}")
        print(f"📂  Open: {output_path.resolve()}")
        print(f"💡  Keyboard: \u2190 \u2192 navigate \u00b7 Esc/Home contents \u00b7 D/T theme \u00b7 B Bible overlay")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()