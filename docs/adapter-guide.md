# ADTM Adapter Guide

Review date: 2026-04-24.

ADTM runs document converters as adapters, normalizes each candidate into the
same staging shape, scores the candidates, and promotes one winner. The default
adapter set is intentionally small:

- Default: `inhouse`
- First-class optional: `markitdown`, `docling`, `unstructured`, `pandoc`,
  `marker`

Optional means explicit, documented, and supported. It does not mean neglected.
The optional adapters remain useful for diagnostics, benchmark runs, and
documents where another converter has a better opinion than the default path.

## Selection Policy

Use the default `inhouse` adapter when you need a fast, local, predictable
conversion path with no external converter binaries.

Use an explicit adapter list when you want tournament comparison, adapter
diagnostics, or a format-specific external tool. Missing optional tools produce
adapter-level failures; they do not make the whole tournament fail.

Use the full adapter pool only for benchmark or diagnostic runs. On the
2026-04-23 benchmark, `inhouse` won most documents and was much faster than the
eligible external adapters, so it remains the only default adapter.

## Adapter Summary

| Adapter | Install boundary | Typical input support | Image behavior | 2026-04-23 benchmark signal | License boundary |
|---|---|---|---|---|---|
| `inhouse` | Base ADTM package | PDF, DOCX, HTML, TXT | Package-native staging; annotates image dimensions when images are present | Default: 14/14 gate passes in default smoke, 10/14 wins in side-by-side run, 42.170 pages/sec | ADTM code is Apache-2.0; required PyMuPDF dependency needs final AGPL/commercial release review |
| `markitdown` | `pip install markitdown` | PDF, DOCX, PPTX, XLSX, HTML, TXT, EPUB, ZIP | Usually text-first; ADTM creates `images/`, but extracted image files are often absent | Optional: 12/14 gate passes, 0 wins, 4.201 pages/sec | Microsoft MarkItDown code is MIT; optional upstream OCR/cloud/LLM features can add separate terms and costs |
| `docling` | `pip install docling` | PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, TXT | Exports referenced images; ADTM rewrites them into `images/` | First-class optional: 4/14 wins, but slow overall at 0.932 pages/sec | Docling code is MIT; model usage can carry separate model terms |
| `unstructured` | `pip install "unstructured[all-docs]"` plus system deps as needed | PDF, DOCX, PPTX, XLSX, HTML, TXT, Markdown, RTF, EPUB, XML, JSON, CSV, TSV | Current ADTM adapter is text-first and does not extract image files | Optional: 12/14 gate passes, 0 wins, 6.162 pages/sec | Unstructured code is Apache-2.0; broad extras have a large transitive/system dependency footprint |
| `pandoc` | Install `pandoc` CLI | HTML, DOCX, Markdown, TXT, RST, AsciiDoc | Does not extract images; ADTM creates an empty `images/` directory | Optional, limited eligibility: very fast when applicable, 1/14 gate pass, 0 wins | Pandoc is GPL-2.0-or-later; keep it as an external executable boundary |
| `marker` | `pip install marker-pdf` and ensure `marker_single` is on `PATH` | PDF | Extracts PDF images and ADTM rewrites paths into `images/` | Optional; unavailable or unsupported in the 2026-04-23 benchmark environment | Marker code is GPL-3.0 and model weights have separate terms; do not vendor or default-enable without review |

The benchmark signal is directional, not a universal claim. Speeds and wins are
date-, hardware-, dependency-, corpus-, and mode-dependent.

## Stable Output Contract

Every adapter must write or normalize into this staging layout:

```text
<staging>/<adapter>/
|-- index.md
|-- images/
`-- adapter_result.json
```

The promoted winner has this layout:

```text
<staging>/winner/
|-- index.md
|-- images/
|-- qa_report.json
`-- remediation_plan.json  # only when judge findings produced one
```

This contract is more important than any single converter. It lets host
applications consume one stable result even when upstream tools behave
differently.

## Adapter Notes

### inhouse

`inhouse` wraps ADTM's own converter modules directly. It is the default because
it is fast, local, predictable, and integrated with ADTM's staging conventions.

Use it for normal conversions and for CI smoke tests. It is not a proof that
external adapters are unnecessary; it is the best current default based on the
dated benchmark evidence.

### markitdown

`markitdown` is useful when you want broad Microsoft MarkItDown format coverage
through a simple CLI boundary.

Install:

```bash
python -m pip install markitdown
```

Use it explicitly when you want another text-first conversion opinion. Do not
expect ADTM's MarkItDown adapter to preserve extracted image files; upstream
MarkItDown often routes visual content through text/OCR-style handling rather
than stable image extraction.

### docling

`docling` is useful when document structure and referenced image export matter
more than raw speed.

Install:

```bash
python -m pip install docling
```

Use it explicitly for comparison runs, image-export checks, and documents where
the default converter loses structure. Keep it out of the default adapter set
until dated benchmark evidence justifies the latency.

### unstructured

`unstructured` is useful when you want the Unstructured partitioning ecosystem
and broad file-type coverage.

Install:

```bash
python -m pip install "unstructured[all-docs]"
```

Some formats also require system tools such as `libmagic`, `poppler`,
`tesseract`, or `libreoffice`. ADTM currently routes PDFs through
Unstructured's text-first `fast` strategy so hosts without OCR stacks can still
run the adapter.

### pandoc

`pandoc` is useful as a deterministic text-centric normalizer when the source
format maps cleanly into Pandoc's input formats.

Install Pandoc with your OS package manager or upstream release package, then
verify:

```bash
pandoc --version
```

It can be very fast, but it is not a general PDF/image extraction adapter and
was rarely eligible in the 2026-04-23 corpus.

### marker

`marker` is useful for PDF layout conversion experiments when its code, model,
and runtime footprint are acceptable for your environment.

Install:

```bash
python -m pip install marker-pdf
marker_single --help
```

Keep it explicit. It has GPL/model-license boundaries and can involve model
downloads or local acceleration expectations that do not belong in ADTM's base
install.

## Running Optional Adapter Smokes

Use the focused commands in
[`adapter-integration-tests.md`](adapter-integration-tests.md) after installing
an optional adapter. The single-adapter smoke is the right pass/fail check. The
full-pool diagnostic is useful for discovery, but it should print missing
optional tools rather than requiring every adapter to be installed.

## Related Docs

- Benchmark snapshot:
  [`benchmarks/adapter-corpus-2026-04-23.md`](benchmarks/adapter-corpus-2026-04-23.md)
- Optional adapter smoke commands:
  [`adapter-integration-tests.md`](adapter-integration-tests.md)
- Dependency and license notes:
  [`dependency-license-notes.md`](dependency-license-notes.md)
