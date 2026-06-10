# ADTM Troubleshooting

Review date: 2026-04-24.

This guide covers common ADTM setup and conversion issues. It assumes the
public default install, where `inhouse` is the only default adapter and external
converters are opt-in.

## Quick Checks

From the package root:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

Run the default no-cloud smoke:

```bash
python - <<'PY'
from pathlib import Path
from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_LIGHT

source = Path("examples/quickstart/field-note.txt")
staging = Path("/tmp/adtm-troubleshooting-smoke")
result = run_full_tournament(source, staging, audit_mode=AUDIT_MODE_LIGHT, timeout_s=60)
print(result.to_dict())
assert result.winner == "inhouse", result.to_dict()
assert (staging / "winner" / "index.md").exists()
PY
```

This smoke should not require optional converter binaries, API keys, cloud LLM
credits, local model weights, or private documents.

## Paragraph Fragmentation Warnings

Symptom:

```text
paragraph_not_row_sliced: Likely row-sliced paragraph fragmentation detected.
```

This warning means programmatic QA found prose that looks like visual rows split
into separate Markdown paragraphs. It is not a hard gate. The warning adds a
modest score penalty so cleaner candidates are preferred, and the built-in
paragraph-continuity repair may remove the warning by publishing an accepted
`index_fixed.md`. The detector uses Latin-script lowercase and continuation-word
signals, so it can miss fragmentation in caseless scripts or languages outside
those heuristics.

The warning is independent of `--paragraph-repair`. It always uses conservative
default thresholds, so running with `--paragraph-repair off` still reports
row-sliced prose — `off` disables the auto-fix, not the quality signal. Repair
clears the warning only by fixing the content (publishing a clean
`index_fixed.md`), never by suppressing the check.

Checks:

- Compare the adapter's raw staging `index.md` with `index_fixed.md` when one
  exists.
- Re-run with `--paragraph-repair off` only when you need to inspect raw adapter
  Markdown or confirm whether repair changed the published output.
- If the warning is a false positive, keep the source synthetic and minimal in
  the bug report; include the bounded QA details, not private document text.

## PyMuPDF Notes

`PyMuPDF` is a required runtime dependency because ADTM's default PDF path uses
it for PDF text, image, page, and rendering operations.

Important release note: PyMuPDF is the main dependency-license review item for
the initial public release. Current PyPI metadata lists PyMuPDF as dual
licensed under GNU AGPL-3.0 or Artifex Commercial License. See
[`dependency-license-notes.md`](dependency-license-notes.md) before packaging
or redistributing ADTM.

### Import Or Install Failures

Symptom:

```text
ModuleNotFoundError: No module named 'fitz'
```

Checks:

```bash
python -m pip show PyMuPDF
python - <<'PY'
import fitz
print(fitz.__doc__.splitlines()[0])
PY
```

Fixes:

- Install ADTM into the active environment rather than relying on a different
  shell's virtualenv.
- Reinstall the package dependencies with `python -m pip install -e .` from the
  package root.
- If a platform wheel is unavailable, resolve the local Python/platform build
  issue before debugging ADTM itself.

### `pymupdf_layout` Recommendation Warning

Some PyMuPDF table/layout APIs can print a recommendation similar to:

```text
Consider using the pymupdf_layout package for a greatly improved page layout analysis.
```

ADTM's classifier now suppresses the noisy recommendation before bounded table
heuristics. Do not add `pymupdf-layout` or PyMuPDF4LLM-style layout stacks to
the default install to silence this warning. A 2026-04-23 local test found no
default quality win large enough to justify the license and performance
footprint.

Policy: keep those layout packages explicit and opt-in only, with exact version,
license, model, dependency, and benchmark notes.

### Slow Large PDFs

Large PDFs can be slow even with the default adapter. If the run is unexpectedly
slow:

- Confirm which adapters were requested. A full-pool run can spend most of its
  time in optional external adapters.
- Check `adapter_result.json` timing fields under each adapter staging
  directory.
- Prefer `inhouse` only for routine runs and reserve `docling`, `unstructured`,
  `markitdown`, `pandoc`, and `marker` for explicit diagnostics or benchmarks.

## LibreOffice Missing for DOCX

ADTM's `inhouse` adapter converts DOC/DOCX/ODT/RTF by shelling out to
LibreOffice headless, then processing the resulting PDF. LibreOffice is not
installed by the ADTM package itself.

Symptom:

```text
RuntimeError: LibreOffice conversion failed (exit 1):
```

or:

```text
FileNotFoundError: [Errno 2] No such file or directory: 'libreoffice'
```

Checks:

```bash
which libreoffice
libreoffice --version
```

Fixes:

- Install LibreOffice with your OS package manager:

  ```bash
  # Debian/Ubuntu
  sudo apt-get install libreoffice-core libreoffice-writer
  ```

- Confirm `libreoffice` is on `PATH` for the running process after installation.
- PDF, HTML, and TXT conversion does not need LibreOffice; only DOC/DOCX/ODT/RTF
  routes through it.

## Optional Adapter Problems

Optional adapter failures should appear as adapter-level errors. They should
not crash the whole tournament.

Run the focused adapter smoke from
[`adapter-integration-tests.md`](adapter-integration-tests.md) for the adapter
you are debugging. Use `/tmp` or another ignored directory for staging output.

### Missing CLI Or Package

Typical symptoms:

```text
markitdown CLI not found. Install with: pip install markitdown
docling CLI not found. Install with: pip install docling
pandoc CLI not found. Install pandoc and ensure it is on PATH.
marker_single CLI not found. Install marker and ensure it is on PATH.
unstructured package not installed.
```

Checks:

```bash
which markitdown || true
which docling || true
which pandoc || true
which marker_single || true
python -m pip show unstructured || true
```

Fixes:

- Install the optional adapter in the same Python environment that runs ADTM.
- For CLI adapters, confirm the executable is on `PATH` for the running process.
- For system tools such as Pandoc, prefer your OS package manager or upstream
  installer and then verify with `pandoc --version`.
- Keep optional adapters out of the default install unless a dated benchmark and
  license review justify changing the default footprint.

### Unsupported Extension

Symptoms:

```text
Unsupported extension: .ext
```

Fixes:

- Check the adapter's supported formats in [`adapter-guide.md`](adapter-guide.md).
- Use an explicit adapter that supports the source format.
- If the format should be supported, add a focused regression test before
  changing adapter routing.

### Timeout

Symptoms:

```text
Timed out after 120s
```

Fixes:

- Increase the per-adapter timeout only for explicit diagnostic runs.
- Check whether a slower optional adapter is being run by accident.
- For `docling`, `unstructured`, or `marker`, test a small public fixture before
  running large private documents.
- Record date, hardware, dependency versions, source size, adapter list, and
  timeout when reporting the issue.

## Missing Images

ADTM normalizes every adapter into an `images/` directory, but not every adapter
extracts image files.

Expected behavior by adapter:

| Adapter | Image expectation |
|---|---|
| `inhouse` | Preserves images when the package-native converter extracts them. |
| `docling` | Exports referenced image files and ADTM rewrites them into `images/`. |
| `marker` | Extracts PDF images and ADTM rewrites paths into `images/`. |
| `markitdown` | Often text-first/OCR-style; `images/` may be empty. |
| `unstructured` | Current ADTM adapter is text-first; `images/` stays empty. |
| `pandoc` | Does not extract images; `images/` stays empty. |

If Markdown references images but files are missing:

- Inspect `<staging>/<adapter>/index.md` for image paths.
- Inspect `<staging>/<adapter>/images/`.
- Inspect `<staging>/<adapter>/adapter_result.json` for `status`,
  `error_message`, and `stderr`.
- Try `docling` or `marker` explicitly for image-heavy PDFs when their license
  and install footprint are acceptable.
- Report a minimal synthetic reproduction if the adapter claims success but
  produces broken image references.

MarkItDown note: MarkItDown often takes a lossy text/OCR-oriented path for
visual content instead of extracting stable image files. Treat that as an
adapter behavior difference, not an ADTM staging failure.

## LLM Judge Problems

If `audit_mode="auto"` does not run a judge, first check whether required judge
settings are present. Missing judge settings make the orchestrator fall back to
light mode.

Required local judge variables:

```bash
export ANYDOC2MD_JUDGE_PROVIDER="lm_studio"
export ANYDOC2MD_JUDGE_URL="http://127.0.0.1:1234/v1"
export ANYDOC2MD_JUDGE_MODEL="model-id"
```

Required cloud key variables:

```bash
export OPENAI_API_KEY="..."
export DEEPSEEK_API_KEY="..."
export CLAUDE_API_KEY="..."
```

Do not put real API keys in bug reports, logs, screenshots, or committed files.
Use [`llm-judge-setup.md`](llm-judge-setup.md) for provider setup, concurrency
checks, and dated cost-reporting commands.

## Generated Artifacts

Keep generated output out of git:

- adapter staging directories
- `/tmp/adtm-*` smoke and benchmark outputs
- benchmark JSON and Markdown dumps
- virtualenvs
- downloaded archives
- model weights
- private source documents
- `.env` files and API keys

If a generated artifact is useful for public documentation, summarize it in a
curated dated doc instead of committing raw local output.

## Reporting Issues

Use the public issue templates for conversion-quality bugs and adapter
installation failures. Good reports include:

- source format, page count, and file size
- adapter list and audit mode
- relevant `adapter_result.json` excerpt
- whether images, OCR, tables, equations, or multi-column layout are involved
- date, hardware, dependency versions, and cloud provider/model when relevant
- cost context for cloud-judge runs, including provider billing data if
  available

Do not upload sensitive documents publicly. Prefer a minimal synthetic document
that preserves the failing structure without private content.
