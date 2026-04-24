# ADTM Optional Adapter Integration Tests

These commands are local, opt-in checks for optional converter adapters. They
are not part of the default CI contract because they can require external
binaries, large Python dependency stacks, OCR tools, model downloads, or
license terms outside ADTM's Apache-2.0 package code.

The default package test remains:

```bash
cd packages/any-doc-to-md
python -m pip install -e ".[test]"
python -m pytest -q
```

## Shared Smoke Helper

Use this helper from the package root. It runs exactly one adapter and asserts
that the adapter produced the normalized ADTM staging shape.

```bash
ADTM_ADAPTER=inhouse \
ADTM_SOURCE=examples/quickstart/field-note.txt \
PYTHONPATH=src python - <<'PY'
from pathlib import Path
import os

from anydoc2md.format_converters.tournament.runner import run_tournament

adapter = os.environ["ADTM_ADAPTER"]
source = Path(os.environ["ADTM_SOURCE"])
staging = Path("/tmp") / f"adtm-{adapter}-integration"

result = run_tournament(
    source,
    staging,
    adapters=[adapter],
    timeout_s=120,
    max_workers=1,
)[0]

print(result.to_dict())
assert result.status == "ok", result.to_dict()
assert (staging / adapter / "index.md").exists()
PY
```

The helper writes under `/tmp/adtm-<adapter>-integration`. Keep those generated
outputs out of git.

## Adapter Commands

### inhouse

No external converter install is required.

```bash
ADTM_ADAPTER=inhouse \
ADTM_SOURCE=examples/quickstart/field-note.txt \
PYTHONPATH=src python - <<'PY'
from pathlib import Path
import os
from anydoc2md.format_converters.tournament.runner import run_tournament

adapter = os.environ["ADTM_ADAPTER"]
source = Path(os.environ["ADTM_SOURCE"])
staging = Path("/tmp") / f"adtm-{adapter}-integration"
result = run_tournament(source, staging, adapters=[adapter], timeout_s=120, max_workers=1)[0]
print(result.to_dict())
assert result.status == "ok", result.to_dict()
assert (staging / adapter / "index.md").exists()
PY
```

### markitdown

Install MarkItDown in your local test environment.

```bash
python -m pip install markitdown

ADTM_ADAPTER=markitdown \
ADTM_SOURCE=examples/quickstart/field-note.txt \
PYTHONPATH=src python - <<'PY'
from pathlib import Path
import os
from anydoc2md.format_converters.tournament.runner import run_tournament

adapter = os.environ["ADTM_ADAPTER"]
source = Path(os.environ["ADTM_SOURCE"])
staging = Path("/tmp") / f"adtm-{adapter}-integration"
result = run_tournament(source, staging, adapters=[adapter], timeout_s=120, max_workers=1)[0]
print(result.to_dict())
assert result.status == "ok", result.to_dict()
assert (staging / adapter / "index.md").exists()
PY
```

### docling

Install Docling in your local test environment. Docling may install or use model
assets depending on version and input type; check upstream license and model
notes before using it in a redistributed product.

```bash
python -m pip install docling

ADTM_ADAPTER=docling \
ADTM_SOURCE=examples/quickstart/field-note.txt \
PYTHONPATH=src python - <<'PY'
from pathlib import Path
import os
from anydoc2md.format_converters.tournament.runner import run_tournament

adapter = os.environ["ADTM_ADAPTER"]
source = Path(os.environ["ADTM_SOURCE"])
staging = Path("/tmp") / f"adtm-{adapter}-integration"
result = run_tournament(source, staging, adapters=[adapter], timeout_s=120, max_workers=1)[0]
print(result.to_dict())
assert result.status == "ok", result.to_dict()
assert (staging / adapter / "index.md").exists()
PY
```

### unstructured

Install only what you need for the input types under test. Broad document
support can require `unstructured[all-docs]` plus system packages such as
`libmagic`, `poppler`, `tesseract`, and `libreoffice`.

```bash
python -m pip install "unstructured[all-docs]"

ADTM_ADAPTER=unstructured \
ADTM_SOURCE=examples/quickstart/field-note.txt \
PYTHONPATH=src python - <<'PY'
from pathlib import Path
import os
from anydoc2md.format_converters.tournament.runner import run_tournament

adapter = os.environ["ADTM_ADAPTER"]
source = Path(os.environ["ADTM_SOURCE"])
staging = Path("/tmp") / f"adtm-{adapter}-integration"
result = run_tournament(source, staging, adapters=[adapter], timeout_s=120, max_workers=1)[0]
print(result.to_dict())
assert result.status == "ok", result.to_dict()
assert (staging / adapter / "index.md").exists()
PY
```

### pandoc

Install the Pandoc CLI with your OS package manager or from upstream releases,
then verify it is on `PATH`.

```bash
pandoc --version

ADTM_ADAPTER=pandoc \
ADTM_SOURCE=examples/quickstart/field-note.txt \
PYTHONPATH=src python - <<'PY'
from pathlib import Path
import os
from anydoc2md.format_converters.tournament.runner import run_tournament

adapter = os.environ["ADTM_ADAPTER"]
source = Path(os.environ["ADTM_SOURCE"])
staging = Path("/tmp") / f"adtm-{adapter}-integration"
result = run_tournament(source, staging, adapters=[adapter], timeout_s=120, max_workers=1)[0]
print(result.to_dict())
assert result.status == "ok", result.to_dict()
assert (staging / adapter / "index.md").exists()
PY
```

### marker

Marker is PDF-oriented and can involve code and model license constraints. Use
the committed probe PDF for a minimal smoke.

```bash
python -m pip install marker-pdf
marker_single --help

ADTM_ADAPTER=marker \
ADTM_SOURCE=src/anydoc2md/probe_assets/probe_source_reference.pdf \
PYTHONPATH=src python - <<'PY'
from pathlib import Path
import os
from anydoc2md.format_converters.tournament.runner import run_tournament

adapter = os.environ["ADTM_ADAPTER"]
source = Path(os.environ["ADTM_SOURCE"])
staging = Path("/tmp") / f"adtm-{adapter}-integration"
result = run_tournament(source, staging, adapters=[adapter], timeout_s=300, max_workers=1)[0]
print(result.to_dict())
assert result.status == "ok", result.to_dict()
assert (staging / adapter / "index.md").exists()
PY
```

## Full Explicit Pool Diagnostic

This command runs all implemented adapters that are available in the current
environment. It prints failures instead of asserting that every optional adapter
is installed.

```bash
PYTHONPATH=src python - <<'PY'
from pathlib import Path

from anydoc2md.format_converters.tournament.runner import (
    available_adapter_names,
    run_tournament,
)

source = Path("examples/quickstart/field-note.txt")
staging = Path("/tmp/adtm-all-adapters-text-smoke")
results = run_tournament(
    source,
    staging,
    adapters=available_adapter_names(),
    timeout_s=120,
    max_workers=4,
)

for result in sorted(results, key=lambda item: item.method_name):
    print(result.method_name, result.status, result.error_message)
PY
```

Use the single-adapter commands for pass/fail checks. Use the full-pool
diagnostic when changing adapter discovery, error handling, or documentation.
