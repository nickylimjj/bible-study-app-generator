/**
 * Client-side PDF text extraction (PDF.js) tuned to approximate pymupdf's
 * page.get_text() plain-text output closely enough for parser.js's
 * line-sensitive regex rules (e.g. "section headers must be on their own
 * line") to behave the same way.
 *
 * Exposes `window.BibleDeckPdfExtract.extractTextFromPdf(arrayBuffer)`.
 */
(function (global) {
  'use strict';

  var Y_TOLERANCE = 2; // px — items within this Y delta are treated as the same line
  var PARAGRAPH_GAP_RATIO = 1.4; // line gaps bigger than this multiple of the page's typical line pitch get a blank line

  function median(nums) {
    if (!nums.length) return 0;
    var sorted = nums.slice().sort(function (a, b) { return a - b; });
    var mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function reconstructPageText(textContent) {
    var items = textContent.items;
    if (!items.length) return '';

    // Group items into rows by Y position (PDF space: Y increases upward).
    var rows = [];
    var currentRow = null;

    items.forEach(function (item) {
      if (typeof item.str !== 'string') return;
      var y = item.transform[5];
      var x = item.transform[4];
      if (currentRow && Math.abs(currentRow.y - y) <= Y_TOLERANCE) {
        currentRow.items.push({ x: x, str: item.str, width: item.width, height: item.height });
      } else {
        currentRow = { y: y, items: [{ x: x, str: item.str, width: item.width, height: item.height }] };
        rows.push(currentRow);
      }
    });

    // Top-to-bottom reading order.
    rows.sort(function (a, b) { return b.y - a.y; });

    var lineTexts = [];
    rows.forEach(function (row) {
      row.items.sort(function (a, b) { return a.x - b.x; });
      var text = '';
      var lastEnd = null;
      row.items.forEach(function (it) {
        if (lastEnd !== null) {
          var gap = it.x - lastEnd;
          var threshold = (it.height || 10) * 0.2;
          if (gap > threshold && !/\s$/.test(text) && !/^\s/.test(it.str)) {
            text += ' ';
          }
        }
        text += it.str;
        lastEnd = it.x + (it.width || 0);
      });
      lineTexts.push(text);
    });

    // Insert a blank line wherever the vertical gap between consecutive
    // lines is clearly bigger than this page's typical (most common) line
    // pitch — this is what lets splitParagraphs()'s \n\s*\n rule and the
    // Getting-Started paragraph logic detect paragraph boundaries the same
    // way pymupdf's output does. Comparing against the page's own median
    // gap (rather than per-line glyph height) avoids false positives on
    // ordinary wrapped lines within one paragraph, since a glyph's bounding
    // box is usually noticeably shorter than the actual line pitch a layout
    // engine used.
    var gaps = [];
    for (var g = 0; g + 1 < rows.length; g++) {
      gaps.push(rows[g].y - rows[g + 1].y);
    }
    var typicalPitch = median(gaps.filter(function (gp) { return gp > 0; })) || 10;

    var out = [];
    for (var i = 0; i < rows.length; i++) {
      out.push(lineTexts[i]);
      if (i + 1 < rows.length) {
        var gapY = rows[i].y - rows[i + 1].y;
        if (gapY > typicalPitch * PARAGRAPH_GAP_RATIO) {
          out.push('');
        }
      }
    }

    return out.join('\n');
  }

  function extractTextFromPdf(arrayBuffer) {
    if (!global.pdfjsLib) {
      return Promise.reject(new Error('PDF.js (pdfjsLib) is not loaded.'));
    }
    var loadingTask = global.pdfjsLib.getDocument({ data: arrayBuffer });
    return loadingTask.promise.then(function (doc) {
      var pageTexts = [];
      var chain = Promise.resolve();
      for (var pageNum = 1; pageNum <= doc.numPages; pageNum++) {
        (function (n) {
          chain = chain
            .then(function () { return doc.getPage(n); })
            .then(function (page) { return page.getTextContent(); })
            .then(function (textContent) {
              pageTexts.push(reconstructPageText(textContent));
            });
        })(pageNum);
      }
      return chain.then(function () { return pageTexts.join('\n') + '\n'; });
    });
  }

  global.BibleDeckPdfExtract = {
    extractTextFromPdf: extractTextFromPdf,
    reconstructPageText: reconstructPageText, // exposed for tuning/debugging
  };
})(typeof window !== 'undefined' ? window : globalThis);
