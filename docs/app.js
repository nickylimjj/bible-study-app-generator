/**
 * Glue: wires the upload UI to pdf-extract.js + parser.js, builds the deck
 * HTML the same way generate_deck.py's generate_html() does, renders a live
 * preview, and offers HTML/PDF downloads under matching filenames (same
 * name + folder, as presentation.html's "Open original PDF" button requires).
 */
(function () {
  'use strict';

  var el = {
    dropzone: document.getElementById('dropzone'),
    fileInput: document.getElementById('fileInput'),
    status: document.getElementById('status'),
    summary: document.getElementById('summary'),
    preview: document.getElementById('preview'),
    previewWrap: document.getElementById('previewWrap'),
    downloadHtml: document.getElementById('downloadHtml'),
    downloadPdf: document.getElementById('downloadPdf'),
    downloads: document.getElementById('downloads'),
  };

  var state = {
    pdfFile: null,
    generatedHtml: '',
    filenames: null, // { base, html, pdf }
  };

  function setStatus(msg, isError) {
    el.status.textContent = msg || '';
    el.status.classList.toggle('error', !!isError);
  }

  function escapeHtmlAttr(s) {
    return String(s).replace(/"/g, '&quot;');
  }

  // Mirrors generate_html()'s DECK_TITLE/DECK_PDF_URL/DECK_DATA injection and
  // <title> rewrite, operating on the already-fetched template text.
  function buildDeckHtml(templateHtml, studies, deckTitle, pdfUrl) {
    var dataJson = JSON.stringify(studies, null, 2);
    var deckTitleClean = JSON.stringify(deckTitle);
    var pdfUrlClean = JSON.stringify(pdfUrl || '');

    var deckVarMeta = '<script>var DECK_TITLE = ' + deckTitleClean + '; var DECK_PDF_URL = ' + pdfUrlClean + ';</script>\n';
    var deckVarScript = deckVarMeta + '<script>\nvar DECK_DATA = ' + dataJson + ';\n</script>';

    var html = templateHtml;
    var oldTagPattern = /<script id="deck-data" type="application\/json">[\s\S]*?<\/script>/;
    if (oldTagPattern.test(html)) {
      html = html.replace(oldTagPattern, deckVarScript);
    } else {
      var marker = '<script>\n(function';
      var idx = html.indexOf(marker);
      if (idx === -1) idx = html.indexOf('<script>');
      if (idx !== -1) {
        html = html.slice(0, idx) + deckVarScript + '\n' + html.slice(idx);
      } else {
        html = html.replace('</body>', deckVarScript + '\n</body>');
      }
    }

    var studyCount = studies.length;
    html = html.replace(
      '<title>Bible Study Deck</title>',
      '<title>Bible Study (' + studyCount + ' studies)</title>'
    );

    return html;
  }

  function buildSummary(studies, deckTitle) {
    var lines = [];
    lines.push('<h2>' + escapeHtmlAttr(deckTitle) + '</h2>');
    lines.push('<ul class="summary-list">');
    studies.forEach(function (s, i) {
      var q = 0, c = 0, r = 0;
      s.slides.forEach(function (sl) {
        if (sl.type === 'question' || sl.type === 'implications-questions') q++;
        else if (sl.type === 'commentary') c++;
        else if (sl.type === 'bible-read') r++;
      });
      lines.push(
        '<li>' + (i + 1) + '. ' + escapeHtmlAttr(s.title) + ' — ' + s.slides.length +
        ' slides (' + c + 'C, ' + r + 'R, ' + q + 'Q)</li>'
      );
    });
    lines.push('</ul>');
    el.summary.innerHTML = lines.join('\n');
    el.summary.hidden = false;
  }

  function downloadBlob(filename, blob) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function renderPreview(html) {
    // srcdoc (not a blob: URL) so the preview behaves like a normal same-origin
    // document — blob: URLs are handled inconsistently by some browsers for
    // iframe focus/interaction, which can make clicks inside the preview
    // silently fail to register.
    el.preview.onload = function () {
      try { el.preview.contentWindow.focus(); } catch (e) {}
    };
    el.preview.srcdoc = html;
    el.previewWrap.hidden = false;
  }

  async function handleFile(file) {
    if (!file || file.type !== 'application/pdf') {
      setStatus('Please choose a PDF file.', true);
      return;
    }
    state.pdfFile = file;
    el.summary.hidden = true;
    el.previewWrap.hidden = true;
    el.downloads.hidden = true;

    try {
      setStatus('Reading PDF…');
      var buf = await file.arrayBuffer();

      setStatus('Extracting text…');
      var text = await BibleDeckPdfExtract.extractTextFromPdf(buf);
      if (!text.trim()) {
        throw new Error('No text extracted. The file may be scanned/image-only.');
      }

      setStatus('Parsing studies…');
      var deckTitle = BibleDeckParser.extractDeckTitle(text);
      var studies = BibleDeckParser.parseStudies(text);
      if (!studies.length) {
        throw new Error('No studies found. Check that the PDF uses the expected section headers (Getting Started / Observation & Interpretation / Implications & Obedience).');
      }
      var totalSlides = studies.reduce(function (n, s) { return n + s.slides.length; }, 0);
      if (totalSlides === 0) {
        // Studies were found (titles matched) but every one came back with
        // zero slides — the near-certain cause is a PDF whose embedded fonts
        // lack a proper ligature mapping (common from some PDF exporters).
        // PDF.js's text layer then garbles "ti"/"tt"/"ft" sequences (e.g.
        // "Getting" becomes "GeUng"), so the section-header regexes can
        // never match, even though the Python CLI (pymupdf) reads the same
        // PDF correctly. No in-browser fix recovers the lost characters, so
        // point the user at the working path instead of a broken deck.
        throw new Error(
          'Found ' + studies.length + ' study title(s) but could not extract any slide content. ' +
          'This usually means the PDF’s embedded fonts break text extraction in the browser ' +
          '(a known PDF.js limitation with some PDF exporters) — please use the Python command-line ' +
          'tool instead (scripts/generate_deck.py), which reads this kind of PDF correctly.'
        );
      }

      setStatus('Loading presentation template…');
      var templateResp = await fetch('presentation-template.html');
      if (!templateResp.ok) throw new Error('Could not load presentation-template.html (' + templateResp.status + ')');
      var templateHtml = await templateResp.text();

      var filenames = BibleDeckParser.buildOutputFilenames(deckTitle);
      state.filenames = filenames;

      var html = buildDeckHtml(templateHtml, studies, deckTitle, filenames.pdf);
      state.generatedHtml = html;

      buildSummary(studies, deckTitle);
      renderPreview(html);

      el.downloadHtml.textContent = 'Download ' + filenames.html;
      el.downloadPdf.textContent = 'Download ' + filenames.pdf;
      el.downloads.hidden = false;

      setStatus('Done. Preview below — download both files into the same folder.');
    } catch (err) {
      setStatus('Error: ' + err.message, true);
    }
  }

  el.fileInput.addEventListener('change', function (e) {
    handleFile(e.target.files[0]);
  });

  el.dropzone.addEventListener('click', function () {
    el.fileInput.click();
  });

  ['dragenter', 'dragover'].forEach(function (evt) {
    el.dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      el.dropzone.classList.add('dragover');
    });
  });
  ['dragleave', 'drop'].forEach(function (evt) {
    el.dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      el.dropzone.classList.remove('dragover');
    });
  });
  el.dropzone.addEventListener('drop', function (e) {
    var file = e.dataTransfer.files && e.dataTransfer.files[0];
    handleFile(file);
  });

  el.downloadHtml.addEventListener('click', function () {
    if (!state.generatedHtml || !state.filenames) return;
    downloadBlob(state.filenames.html, new Blob([state.generatedHtml], { type: 'text/html' }));
  });

  el.downloadPdf.addEventListener('click', function () {
    if (!state.pdfFile || !state.filenames) return;
    downloadBlob(state.filenames.pdf, state.pdfFile);
  });
})();
