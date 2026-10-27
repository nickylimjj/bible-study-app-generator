/**
 * Bible Study Deck Generator — parser (JS port of scripts/generate_deck.py)
 *
 * Faithful line-by-line port of the Python parsing logic, including its
 * existing quirks (e.g. the "(Choose...)" filter checks HTML-wrapped text,
 * so it never actually matches — kept as-is to match the CLI's output
 * exactly, not "fixed").
 *
 * Exposes `window.BibleDeckParser` with: parseStudies, extractDeckTitle,
 * buildOutputFilenames.
 */
(function (global) {
  'use strict';

  // ── Section header patterns ──────────────────────────────────────
  var SECTION_HEADERS = [
    ['welcome', /Welcome/i],
    ['getting_started', /Getting Started/i],
    ['observation', /Observation\s*(?:&|and)\s*Interpretation/i],
    ['implications', /Implications?\s*(?:&|and)\s*Obedience/i],
    ['following_jesus', /Following Jesus\s*:\s*Daily Discipleship in Life/i],
  ];

  // ── Known Bible book names (for reference expansion) ───────────────
  var KNOWN_BOOKS_LIST = [
    'Genesis', 'Exodus', 'Leviticus', 'Numbers', 'Deuteronomy',
    'Joshua', 'Judges', 'Ruth', 'Samuel', 'Kings', 'Chronicles',
    'Ezra', 'Nehemiah', 'Esther', 'Job', 'Psalms', 'Psalm',
    'Proverbs', 'Ecclesiastes', 'Song', 'Isaiah', 'Jeremiah',
    'Lamentations', 'Ezekiel', 'Daniel', 'Hosea', 'Joel', 'Amos',
    'Obadiah', 'Jonah', 'Micah', 'Nahum', 'Habakkuk', 'Zephaniah',
    'Haggai', 'Zechariah', 'Malachi',
    'Matthew', 'Mark', 'Luke', 'John', 'Acts',
    'Romans', 'Corinthians', 'Galatians', 'Ephesians', 'Philippians',
    'Colossians', 'Thessalonians', 'Timothy', 'Titus', 'Philemon',
    'Hebrews', 'James', 'Peter', 'Jude', 'Revelation',
    'Gen', 'Ex', 'Lev', 'Num', 'Deut',
    'Josh', 'Judg', 'Ruth', 'Sam', 'Kgs', 'Chr',
    'Ezr', 'Neh', 'Est', 'Job', 'Ps', 'Prov', 'Eccl',
    'Song', 'Isa', 'Jer', 'Lam', 'Ezek', 'Dan', 'Hos',
    'Joel', 'Amos', 'Obad', 'Jon', 'Mic', 'Nah', 'Hab',
    'Zeph', 'Hag', 'Zech', 'Mal',
    'Matt', 'Mk', 'Lk', 'Jn', 'Acts',
    'Rom', 'Cor', 'Gal', 'Eph', 'Phil', 'Col',
    'Thess', 'Tim', 'Tit', 'Philem', 'Heb', 'Jas', 'Pet',
    'Rev',
  ];
  var KNOWN_BOOKS = new Set();
  KNOWN_BOOKS_LIST.forEach(function (b) { KNOWN_BOOKS.add(b); });
  // Add lowercase versions
  Array.from(KNOWN_BOOKS).forEach(function (b) { KNOWN_BOOKS.add(b.toLowerCase()); });
  // Add dotted versions (e.g. "Cor.")
  Array.from(KNOWN_BOOKS).forEach(function (b) {
    if (/^[A-Za-z]+$/.test(b) && b.length > 1) {
      KNOWN_BOOKS.add(b + '.');
      KNOWN_BOOKS.add((b + '.').toLowerCase());
    }
  });

  var NON_BOOK_PREFIXES_LIST = ['cf', 'cf.', 'e.g', 'e.g.', 'i.e', 'i.e.', 'see', 'v', 'vv', 'v.', 'vv.'];
  var NON_BOOK_PREFIXES = new Set();
  NON_BOOK_PREFIXES_LIST.forEach(function (p) {
    NON_BOOK_PREFIXES.add(p);
    NON_BOOK_PREFIXES.add(p.toLowerCase());
  });

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // ── Step 2: Parse text into studies ────────────────────────────────
  function parseStudies(text) {
    text = text.trim();
    if (!text) return [];

    var studies = [];
    var studyPattern = /^(?:Study|Lesson|Session)\s+(\d+)[:\s.\-–—]*\s*(.*?)$/gim;

    var allMatches = [];
    var m;
    while ((m = studyPattern.exec(text)) !== null) {
      var lineNo = (text.slice(0, m.index).match(/\n/g) || []).length;
      allMatches.push({ lineNo: lineNo, match: m, index: m.index, endIndex: m.index + m[0].length, groups: [m[1], m[2]] });
      if (m[0].length === 0) studyPattern.lastIndex++; // avoid infinite loop on zero-length match
    }

    if (allMatches.length === 0) {
      var slides = parseSlidesFromText(text);
      studies.push({ title: 'Study', slides: slides });
      return studies;
    }

    // Filter out TOC entries (those clustered near the top)
    if (allMatches.length >= 3) {
      var tocClusterEnd = 0;
      for (var i = 0; i < allMatches.length; i++) {
        if (allMatches[i].lineNo < 500) {
          tocClusterEnd = allMatches[i].lineNo;
        } else {
          break;
        }
      }
      var hasContentCluster = allMatches.some(function (e) { return e.lineNo > tocClusterEnd + 50; });
      if (tocClusterEnd > 0 && hasContentCluster) {
        var contentStartIdx = allMatches.findIndex(function (e) { return e.lineNo > tocClusterEnd + 50; });
        allMatches = allMatches.slice(contentStartIdx);
      }
    }

    for (var idx = 0; idx < allMatches.length; idx++) {
      var entry = allMatches[idx];
      var studyNum = entry.groups[0];
      var studyTitleLine = (entry.groups[1] || '').trim();
      var studyStart = entry.endIndex;
      var studyEnd = idx + 1 < allMatches.length ? allMatches[idx + 1].index : text.length;
      var studyBody = text.slice(studyStart, studyEnd).trim();

      var titleParts = ['Study ' + studyNum];
      if (studyTitleLine) titleParts.push(studyTitleLine);
      var title = titleParts.join(': ');

      var studyDate = extractStudyDate(studyBody);
      var slides2 = parseSlidesFromStudy(studyBody);
      studies.push({ title: title, date: studyDate, slides: slides2 });
    }

    return studies;
  }

  function parseSlidesFromText(text) {
    // Fallback when no "Study N" headers are found at all — treat the
    // whole document as one unnamed study's Q&A body.
    return parseQAndASection(text, 'Observation & Interpretation');
  }

  // ── Step 3: Parse a single study into slides ────────────────────────
  function parseSlidesFromStudy(text) {
    var slides = [];
    var sections = splitIntoSections(text);
    if (!sections.length) return slides;

    sections.forEach(function (pair) {
      var sectionName = pair[0], sectionText = pair[1];
      if (sectionName === 'following_jesus' || sectionName === 'welcome') return;
      slides = slides.concat(processSection(sectionName, sectionText));
    });

    return slides;
  }

  function splitIntoSections(text) {
    var studyMatch = /^(?:Study|Lesson|Session)\s+\d+/im.exec(text);
    var searchAnchor = studyMatch ? studyMatch.index : 0;
    var textAfterStudy = text.slice(searchAnchor);

    var found = [];
    SECTION_HEADERS.forEach(function (pair) {
      var key = pair[0], pat = new RegExp(pair[1].source, pair[1].flags.indexOf('g') === -1 ? pair[1].flags + 'g' : pair[1].flags);
      var mm;
      while ((mm = pat.exec(textAfterStudy)) !== null) {
        var lineStart = mm.index;
        var isOwnLine = lineStart === 0 || textAfterStudy[lineStart - 1] === '\n';
        if (isOwnLine) {
          found.push([mm.index + searchAnchor, key, mm.index + mm[0].length + searchAnchor]);
        }
        if (mm[0].length === 0) pat.lastIndex++;
      }
    });

    if (!found.length) return [];

    found.sort(function (a, b) { return a[0] - b[0]; });

    var sections = [];
    for (var i = 0; i < found.length; i++) {
      var start = found[i][0], key = found[i][1], headerEnd = found[i][2];
      var end = i + 1 < found.length ? found[i + 1][0] : text.length;
      var headerLineEnd = text.indexOf('\n', headerEnd);
      if (headerLineEnd === -1) headerLineEnd = headerEnd;
      var sectionText = text.slice(headerLineEnd, end).trim();
      sections.push([key, sectionText]);
    }

    return sections;
  }

  function processSection(sectionName, text) {
    var slides = [];
    if (!text.trim()) return slides;

    var displayNames = {
      getting_started: 'Getting Started',
      observation: 'Observation & Interpretation',
      implications: 'Implications & Obedience',
    };
    var displayName = displayNames[sectionName] || sectionName.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });

    if (sectionName === 'getting_started') {
      var paras = splitParagraphs(text);
      if (paras.length) {
        var html = paras.map(function (p) { return '<p>' + p + '</p>'; }).join('');
        slides.push({ type: 'commentary', section: displayName, content: html });
      }
      return slides;
    }

    if (sectionName === 'observation') {
      return parseQAndASection(text, displayName);
    }

    if (sectionName === 'implications') {
      var rawSlides = parseQAndASection(text, displayName);
      var questions = rawSlides.filter(function (s) { return s.type === 'question'; });
      var otherSlides = rawSlides.filter(function (s) { return s.type !== 'question'; });

      // NOTE: faithfully replicates the Python script's existing behavior —
      // this check runs against the already HTML-wrapped content (e.g.
      // "<p>(Choose...") so it never actually matches. Kept as-is on purpose.
      var filteredOthers = otherSlides.filter(function (s) {
        var content = (s.content || '').trim();
        return !(content.startsWith('(Choose') || content.startsWith('(Pick'));
      });

      slides = slides.concat(filteredOthers);

      if (questions.length) {
        var qHtmlParts = questions.map(function (q) {
          return '<div class="implications-question">' + q.content + '</div>';
        });
        slides.push({
          type: 'implications-questions',
          section: displayName,
          content: qHtmlParts.join(''),
        });
      }

      return slides;
    }

    return slides;
  }

  function stripFootnotesFromQuestion(text) {
    text = text.replace(/\s+/g, ' ').trim();
    text = text.replace(/\s+\d{1,3}(?:\s+\d{1,3})?\s*$/, '');
    return text.trim();
  }

  // ── Bible Context Tracking & Reference Expansion ──────────────────

  function parsePassageContext(passage) {
    var m = /^((?:\d\s+)?[A-Za-z][A-Za-z\s]+?)\s+(\d+):/.exec(passage.trim());
    if (m) {
      var book = m[1].trim();
      if (book.endsWith('.')) book = book.slice(0, -1);
      var chapter = parseInt(m[2], 10);
      return [book, chapter];
    }
    return [null, null];
  }

  var NUMBERED_BOOK_PAIRS = [
    '1 corinthians', '2 corinthians', '1 samuel', '2 samuel',
    '1 kings', '2 kings', '1 chronicles', '2 chronicles',
    '1 peter', '2 peter', '1 john', '2 john', '3 john',
    '1 thessalonians', '2 thessalonians', '1 timothy', '2 timothy',
    '1 cor', '2 cor', '1 sam', '2 sam', '1 kgs', '2 kgs',
    '1 chr', '2 chr', '1 pet', '2 pet', '1 jn', '2 jn', '3 jn',
    '1 thess', '2 thess', '1 tim', '2 tim',
  ];

  function isPrecededByBook(text, pos) {
    var before = text.slice(Math.max(0, pos - 50), pos).trim();
    var words = before.match(/[A-Za-z]+\.?/g);
    if (!words || !words.length) return false;

    var last = words[words.length - 1].toLowerCase();
    if (KNOWN_BOOKS.has(last)) return true;

    if (words.length >= 2) {
      var lastTwo = words[words.length - 2].toLowerCase() + ' ' + words[words.length - 1].toLowerCase();
      for (var i = 0; i < NUMBERED_BOOK_PAIRS.length; i++) {
        if (lastTwo.indexOf(NUMBERED_BOOK_PAIRS[i]) === 0) return true;
      }
    }

    if (NON_BOOK_PREFIXES.has(last)) return false;

    var lastWord = words[words.length - 1];
    if (/[A-Z]/.test(lastWord[0]) && lastWord.length > 1) return true;

    return false;
  }

  function expandQuestionRefs(text, book, chapter) {
    if (!book) return text;

    // ── Step 1: Expand bare verse references ──
    text = text.replace(/\b([vV]\.?|[vV][vV]\.?)\s+([\d,\s\-;:]+)/g, function (whole, prefix, refs) {
      refs = refs.trim();
      var segments = refs.split(/(;)/);
      var resultParts = [];
      segments.forEach(function (seg) {
        if (seg === ';') { resultParts.push('; '); return; }
        if (!seg.trim()) return;
        var parts = seg.split(',').map(function (p) { return p.trim(); }).filter(function (p) { return p; });
        var expandedParts = parts.map(function (part) {
          part = part.trim();
          if (!part) return '';
          part = part.replace(/^[vV]\.?\s*/, '');
          if (!part) return '';
          if (/^\d+:\d/.test(part)) {
            return book + ' ' + part;
          }
          return book + ' ' + chapter + ':' + part;
        }).filter(function (p) { return p; });
        resultParts.push(expandedParts.join(', '));
      });
      return resultParts.join('');
    });

    // ── Step 2: Expand short chapter:verse refs without book prefixes ──
    var result = '';
    var i = 0;
    var cvRe = /(\d+):(\d+(?:-\d+)?)/;
    while (i < text.length) {
      var rest = text.slice(i);
      var m = cvRe.exec(rest);
      if (!m) break;

      var absStart = i + m.index;
      var absEnd = i + m.index + m[0].length;

      result += text.slice(i, absStart);

      if (!isPrecededByBook(text, absStart)) {
        result += book + ' ' + m[1] + ':' + m[2];
      } else {
        result += text.slice(absStart, absEnd);
      }

      i = absEnd;
    }
    result += text.slice(i);
    text = result;

    // ── Step 3: Handle ":-" pattern (missing start verse) ──
    text = text.replace(/:-(\d+)/g, ':1-$1');

    // ── Step 4: Wrap expanded refs in bible-ref tags (plain text display) ──
    text = linkBibleRefs(text);

    // ── Step 5: Link comma-separated verse continuations ──
    text = linkCommaContinuations(text);

    return text;
  }

  function linkBibleRefs(text) {
    var pattern = /\b((?:\d\s+)?[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(\d+:\d+(?:-\d+)?)([a-z])?\b/g;
    return text.replace(pattern, function (whole, book, ref, suffix) {
      return (book + ' ' + ref + (suffix || '')).trim();
    });
  }

  function linkCommaContinuations(text) {
    function replaceVerse(whole, verses, offset, full) {
      var preText = full.slice(0, offset);
      var lastRefs = preText.match(/data-ref="([^"]+)"/g);
      if (lastRefs && lastRefs.length) {
        var lastRefAttr = lastRefs[lastRefs.length - 1];
        var dataRef = /data-ref="([^"]+)"/.exec(lastRefAttr)[1];
        var lastColon = dataRef.lastIndexOf(':');
        if (lastColon !== -1) {
          var base = dataRef.slice(0, lastColon + 1);
          var newRef = base + verses;
          return '</a>, <a href="#" class="bible-ref" data-ref="' + newRef + '">' + verses + '</a>';
        }
      }
      return whole;
    }

    while (true) {
      var newText = text.replace(/<\/a>,\s*(\d+(?:-\d+)?)/g, replaceVerse);
      if (newText === text) break;
      text = newText;
    }
    return text;
  }

  // ── Parse Q&A sections with context tracking ──────────────────────

  function parseQAndASection(text, sectionName) {
    sectionName = sectionName || 'Observation & Interpretation';
    var slides = [];
    var lines = text.split('\n');

    var contextBook = null;
    var contextChapter = null;

    function makeSlide(slideType, content, extra) {
      var slide = { type: slideType, section: sectionName, content: content };
      if (extra) Object.assign(slide, extra);
      return slide;
    }

    var buf = [];

    function flushCommentary() {
      if (!buf.length) return;
      var body = buf.filter(function (l) { return l.trim(); }).map(function (l) { return l.trim(); }).join(' ').trim();
      if (body) {
        body = body.replace(/\b\d{1,3}\b(?![:.)])/g, '');
        body = body.replace(/\s{2,}/g, ' ').trim();
        var paras = splitParagraphs(body);
        var html = paras.map(function (p) { return '<p>' + p + '</p>'; }).join('');
        html = linkBibleRefs(html);
        slides.push(makeSlide('commentary', html));
      }
      buf = [];
    }

    var inSidebar = false;
    var sidebarLines = [];

    function flushSidebar() {
      if (!sidebarLines.length) { inSidebar = false; return; }
      var sidebarTitle = '';
      var cleaned = [];
      sidebarLines.forEach(function (sl) {
        var m = /^SIDEBAR\s+(\d+)\s*:\s*(.*)/i.exec(sl);
        if (m && !sidebarTitle) sidebarTitle = m[2].trim();
        if (!/^SIDEBAR\s+\d+\s*:/i.test(sl)) cleaned.push(sl);
      });
      var body = cleaned.join(' ').trim();
      if (body) {
        var label = sidebarTitle ? '[Sidebar — ' + sidebarTitle + ']' : '[Sidebar content]';
        slides.push(makeSlide('commentary', '<p><em>' + label + '</em></p><p>' + body + '</p>'));
      }
      sidebarLines = [];
      inSidebar = false;
    }

    var sidebarDelim = /^——{2,}—*$|^—{3,}$|^-{3,}$/;

    var i = 0;
    while (i < lines.length) {
      var raw = lines[i];
      var line = raw.trim();

      if (sidebarDelim.test(line)) {
        if (inSidebar) {
          flushSidebar();
        } else {
          flushCommentary();
          var lookahead = lines.slice(i, i + 5).join('');
          if (/SIDEBAR\s+\d+\s*:/i.test(lookahead)) {
            inSidebar = true;
          } else {
            i += 1;
            continue;
          }
        }
        i += 1;
        continue;
      }

      if (inSidebar) {
        if (line) sidebarLines.push(line);
        i += 1;
        continue;
      }

      if (!line) {
        i += 1;
        continue;
      }

      var readMatch = /^Read\s+(.+?)(?:\s*\.\s*)?$/.exec(line);
      if (readMatch) {
        flushCommentary();
        var passage = readMatch[1].trim();

        var ctx = parsePassageContext(passage);
        if (ctx[0]) {
          contextBook = ctx[0];
          contextChapter = ctx[1];
        }

        slides.push(makeSlide('bible-read', 'Read ' + passage, { passage: passage }));
        i += 1;
        continue;
      }

      var qMatch = /^(\d+)[.)]\s/.exec(line);
      if (qMatch) {
        var qNum = parseInt(qMatch[1], 10);
        if (qNum > 50) {
          buf.push(raw);
          i += 1;
          continue;
        }

        flushCommentary();

        var rest = line.slice(qMatch[0].length);
        var qText = qNum + '. ' + rest;

        i += 1;
        while (i < lines.length) {
          var nextRaw = lines[i];
          var nextLine = nextRaw.trim();
          if (!nextLine) break;
          if (sidebarDelim.test(nextLine)) break;
          if (/^SIDEBAR\s+\d+\s*:/i.test(nextLine)) break;
          if (/^Read\s+/.test(nextLine)) break;
          if (/^\d+[.)]\s/.test(nextLine)) break;
          qText += ' ' + nextLine;
          i += 1;
        }

        qText = qText.replace(/\s+/g, ' ').trim();
        qText = stripFootnotesFromQuestion(qText);
        qText = expandQuestionRefs(qText, contextBook, contextChapter);
        slides.push(makeSlide('question', qText));
        continue;
      }

      buf.push(raw);
      i += 1;
    }

    flushCommentary();
    if (inSidebar) flushSidebar();
    return slides;
  }

  function splitParagraphs(text) {
    if (!text.trim()) return [];
    var paras = text.split(/\n\s*\n/).map(function (p) { return p.trim(); }).filter(function (p) { return p; });
    return paras.length ? paras : [text];
  }

  // ── Deck title extraction ───────────────────────────────────────────
  function extractDeckTitle(text) {
    var studyMatch = /^(?:Study|Lesson|Session)\s+\d+/im.exec(text);
    var preText;
    if (studyMatch) {
      preText = text.slice(0, studyMatch.index).trim();
      var preLines = preText.split('\n').map(function (l) { return l.trim(); }).filter(function (l) { return l; });
      if (preLines.length > 20) preText = preLines.slice(0, 20).join('\n');
    } else {
      preText = text.slice(0, 3000);
    }

    var lines = preText.split('\n').map(function (l) { return l.trim(); }).filter(function (l) { return l; });
    var copyrightMarkers = [
      '©', 'copyright', 'all rights reserved', 'no part',
      'this publication', 'these studies are adapted', 'scripture quotations',
      'this resource was downloaded', 'permission', 'arpc@', 'website:',
    ];
    var titleLines = [];
    var seenTitleStart = false;

    for (var idx = 0; idx < lines.length; idx++) {
      var line = lines[idx];
      if (line.length < 5) continue;
      var lineLower = line.toLowerCase();
      var isCopyright = copyrightMarkers.some(function (marker) { return lineLower.indexOf(marker) !== -1; });
      if (isCopyright) break;

      if (line === line.toUpperCase() && /[A-Z]/.test(line) && line.length > 10) {
        if (seenTitleStart) break;
        continue;
      }

      if (/^[A-Z][a-z]+\s*[-–—]\s*[A-Z][a-z]+\s+\d{4}/.test(line)) break;
      if (/^\d{4}$/.test(line)) break;

      seenTitleStart = true;
      titleLines.push(line);

      var openCount = (line.match(/\(/g) || []).length;
      var closeCount = (line.match(/\)/g) || []).length;
      if (openCount === closeCount && closeCount > 0 && line.endsWith(')')) break;
    }

    if (titleLines.length) {
      var title = titleLines.join(' ');
      title = title.replace(/\s+/g, ' ').trim().replace(/\.$/, '');
      title = title.replace(/\s+\d{4}\s*$/, '').trim();
      title = title.replace(/\s+[A-Z][a-z]+\s*-\s*[A-Z][a-z]+\s+\d{4}\s*$/, '').trim();
      if (title) return title;
    }
    return 'Bible Study';
  }

  function extractStudyDate(text) {
    var firstLine = text ? text.split('\n')[0].trim() : '';
    var m = /^(?:Week\s+Of\s+)?([A-Z][a-z]+ \d+)\s*[-–—]\s*(?:([A-Z][a-z]+) )?(\d+)/.exec(firstLine);
    if (m) {
      var month1Day = m[1], month2 = m[2], day2 = m[3];
      if (month2) return 'Week Of ' + month1Day + ' — ' + month2 + ' ' + day2;
      var month1 = month1Day.split(' ')[0];
      return 'Week Of ' + month1 + ' ' + month1Day.split(' ')[1] + ' — ' + day2;
    }
    var m2 = /^(?:Week\s+Of\s+)?([A-Z][a-z]+ \d+)$/.exec(firstLine);
    if (m2) return m2[1];

    var lines = text.split('\n').map(function (l) { return l.trim(); }).filter(function (l) { return l; });
    for (var idx = 1; idx < Math.min(4, lines.length); idx++) {
      var candidate = lines[idx];
      var mc = /^(?:Week\s+Of\s+)?([A-Z][a-z]+ \d+)\s*[-–—]\s*(?:([A-Z][a-z]+) )?(\d+)/.exec(candidate);
      if (mc) {
        var md = mc[1], mo2 = mc[2], dy2 = mc[3];
        if (mo2) return 'Week Of ' + md + ' — ' + mo2 + ' ' + dy2;
        var mo1 = md.split(' ')[0];
        return 'Week Of ' + mo1 + ' ' + md.split(' ')[1] + ' — ' + dy2;
      }
      var mc2 = /^(?:Week\s+Of\s+)?([A-Z][a-z]+ \d+)$/.exec(candidate);
      if (mc2) return mc2[1];
    }

    return '';
  }

  // ── Output filename convention (mirrors main()'s book_name/month/year slug) ──
  function buildOutputFilenames(deckTitle) {
    var bookName = 'study';
    if (deckTitle) {
      var m = /\(([^)]+)\)/.exec(deckTitle);
      if (m) {
        var innerClean = m[1].trim().replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
        if (innerClean) bookName = innerClean;
      } else {
        var firstWord = deckTitle.split(/\s+/)[0];
        bookName = firstWord.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
      }
    }
    if (!bookName || bookName.length < 2) bookName = 'study';

    var now = new Date();
    var monthAbbr = now.toLocaleString('en-US', { month: 'short' }).toLowerCase();
    var year4d = String(now.getFullYear());
    var fileBase = bookName + '_' + monthAbbr + year4d;
    return { base: fileBase, html: fileBase + '.html', pdf: fileBase + '.pdf' };
  }

  global.BibleDeckParser = {
    parseStudies: parseStudies,
    extractDeckTitle: extractDeckTitle,
    buildOutputFilenames: buildOutputFilenames,
    escapeHtml: escapeHtml,
    // exposed for unit-style console testing
    _internal: {
      splitIntoSections: splitIntoSections,
      parseQAndASection: parseQAndASection,
      expandQuestionRefs: expandQuestionRefs,
      extractStudyDate: extractStudyDate,
    },
  };
})(typeof window !== 'undefined' ? window : globalThis);
