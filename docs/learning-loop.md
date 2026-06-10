# ADTM Learning Loop

Review date: `2026-04-25`

ADTM is not only a converter. It is a way to turn conversion failures into
evidence, tests, and repeatable fixes.

The short version for decision makers:

- Most document pipelines silently trust one converter.
- ADTM makes converters compete and records why one output won.
- When ADTM sees a new class of failure, it can preserve evidence, write a
  remediation plan, and generate reviewable hook scaffolds.
- A human or coding agent then turns that evidence into a deterministic test
  and a fix.
- The next run benefits from what the previous run learned.

That is the important trick: ADTM does not pretend bad conversions disappear.
It makes them useful.

## What ADTM Can And Cannot Do

ADTM can detect several kinds of conversion issues today:

- hard failures such as missing `index.md`, empty output, broken image
  references, charset corruption, and sampled PDF text-coverage collapse
- structural Markdown issues such as double bullets, broken numbered lists,
  fragmented headings, detached figure captions, unresolved images, suspicious
  image sizes, repeated headings, and low source-text coverage
- source-fidelity issues found by the LLM judge in `audit_mode="auto"` when a
  judge is configured

ADTM can extend checks today in two ways:

- project-local `qa_extension.py` hooks for document- or project-specific
  checks
- package-level regression tests and built-in QA checks when an issue class is
  common enough to benefit everyone

ADTM can help fix issues today, but it does not secretly rewrite itself:

- it can build a remediation plan from judge findings
- it can author no-op `qa-extensions/*.py` and `fix-extensions/*.py`
  scaffolds from that plan
- a human or coding agent reviews those scaffolds, adds a deterministic check,
  adds or adjusts the converter fix, and reruns ADTM

The runtime does not self-edit package code. That is deliberate. Document
conversion is messy enough without a converter committing code behind your back.

## The Loop

```text
1. Convert
2. Score
3. Audit
4. Capture evidence
5. Write remediation plan
6. Create a regression check
7. Add a converter fix or project-local hook
8. Rerun
9. Promote the best output
10. Keep the lesson
```

For a coding agent, the rule is simple:

```text
Never fix a conversion bug without first making the bug observable.
```

If the issue cannot be observed by a deterministic test, the "fix" is just a
guess wearing a nice jacket.

## Mental Model

ADTM has three kinds of quality signals:

| Signal | Purpose | Example | Result |
|---|---|---|---|
| Hard gate | Disqualify obviously broken output | `index.md` is missing | Candidate cannot win |
| QA check | Score a known issue pattern | Figure caption is far from image | Candidate score gets worse |
| LLM audit | Discover source-fidelity issues not yet encoded | Candidate moved page 4 paragraph before its heading | Finding becomes evidence and remediation plan |

Hard gates are bouncers. QA checks are inspectors. The LLM judge is the witness
you call only when the deterministic machinery has narrowed the case enough to
make the testimony useful.

## Example: The Wandering Figure Caption

This is a hypothetical public example. It uses the same issue class ADTM already
understands: `caption_detachment`.

The source PDF has a figure and caption together:

```text
[pump curve image]
Figure 2. Pump curve under full load.
The curve shows pressure drop after 80% capacity.
```

A candidate Markdown output separates them:

```markdown
<img src="images/pump-curve.png" style="width: 22em">

The curve shows pressure drop after 80% capacity.

... five paragraphs later ...

*Figure 2. Pump curve under full load.*
```

That is not just ugly. It is a semantic bug. A reader now has to guess which
image the caption belongs to. A retrieval system may chunk the caption away
from the image. A downstream LLM may cite the caption without the evidence.

The built-in QA check can flag this:

```python
from anydoc2md.output_qa.checks import check_caption_near_image

result = check_caption_near_image(markdown_text)
assert result.status == "fail"
assert result.name == "caption_near_image"
assert result.violation_type == "caption_detachment"
```

If the issue came from an LLM audit first, the finding would look like this:

```json
{
  "type": "caption_detachment",
  "severity": "major",
  "count": 1,
  "pages": [4],
  "confidence": 0.86,
  "evidence": "Figure 2 caption is separated from the pump curve image.",
  "root_cause": "Image and caption blocks were sorted independently."
}
```

ADTM can turn that into a remediation task:

```json
{
  "violation_type": "caption_detachment",
  "severity": "major",
  "target_adapter": "inhouse",
  "compare_against": "docling",
  "suggested_test": "Add a regression fixture that keeps figure captions adjacent to their images.",
  "suggested_fix_area": "pdf_converter image-caption association",
  "suggested_fix": "Preserve or reconstruct caption proximity during PDF block assembly."
}
```

Then the coding agent has a concrete job:

1. Add a failing test that reproduces the detached caption.
2. Add or adjust the deterministic QA check if the issue class is new.
3. Patch the converter or write a project-local in-house extension.
4. Rerun the tournament.
5. Keep the fix only if the test fails before the change and passes after it.

## Project-Local Fix First

For one project or one document family, start with project-local state. It is
lower risk than changing package behavior for everyone.

A host project can keep state like this:

```text
.any-doc-to-md/
  llm-findings/vendor-report-2026.json
  evidence-packets/vendor-report-2026.json
  qa-extensions/vendor-report-2026.py
  fix-extensions/vendor-report-2026.py
```

`qa-extensions/*.py` can add or disable checks. This example adds a check for a
document family where every `Figure N.` caption must be near an image:

```python
from anydoc2md.output_qa.checks import CheckResult


def get_disabled_checks():
    return []


def get_additional_md_only_checks():
    return [check_vendor_caption_contract]


def get_additional_md_with_dir_checks():
    return []


def get_additional_source_checks():
    return []


def check_vendor_caption_contract(md_text):
    lines = md_text.splitlines()
    image_lines = {i for i, line in enumerate(lines) if "<img" in line}
    failures = []
    for index, line in enumerate(lines):
        if not line.strip().startswith("*Figure "):
            continue
        window = range(max(0, index - 4), min(len(lines), index + 5))
        if not any(candidate in image_lines for candidate in window):
            failures.append(f"Line {index + 1}: {line.strip()[:80]}")

    if failures:
        return CheckResult(
            "vendor_caption_contract",
            1,
            "fail",
            "Figure caption is not near an image.",
            failures,
            violation_type="caption_detachment",
            severity="major",
            confidence=0.80,
        )
    return CheckResult(
        "vendor_caption_contract",
        1,
        "pass",
        "Figure captions are near images.",
    )
```

`fix-extensions/*.py` can patch staging output for that document family.
Keep these hooks small, deterministic, and boring. Clever fixes are hard to
trust.

The structured fields on `CheckResult` are optional and additive. Existing
checks that only return `name`, `layer`, `status`, `message`, and `details`
remain valid; setting `violation_type`, `severity`, and `confidence` makes
reports easier for remediation tooling to group without changing scoring.

Fix hooks are applied to every adapter's output after conversion — not just
inhouse. ADTM runs each fix, scores the result, and keeps it only when the
QA score strictly improves. This means a bad fix for one adapter is discarded
without harming the others.

Treat these hooks as trusted code. A host project should stage reviewed
`qa_extension.py` and `fix_extension.py` files at the document root, not
inside an adapter output directory. ADTM ignores executable hook files found in
adapter staging directories so a converter output cannot smuggle code into the
QA or fix post-processing path.

```python
from pathlib import Path


def apply_fix_extension(source_path, staging_dir, converter_name):
    index_path = Path(staging_dir) / "index.md"
    text = index_path.read_text(encoding="utf-8")
    fixed = text.replace(
        "<img src=\"images/pump-curve.png\" style=\"width: 22em\">\\n\\n"
        "The curve shows pressure drop after 80% capacity.\\n\\n"
        "*Figure 2. Pump curve under full load.*",
        "<img src=\"images/pump-curve.png\" style=\"width: 22em\">\\n"
        "*Figure 2. Pump curve under full load.*\\n\\n"
        "The curve shows pressure drop after 80% capacity.",
    )
    if fixed != text:
        index_path.write_text(fixed, encoding="utf-8")
```

That example is intentionally plain. The point is not to be magical. The point
is to make a specific failure reproducible, reviewable, and reversible.

## When To Promote A Local Lesson Into The Package

Promote a project-local check or fix into package code when:

- the same issue appears in multiple unrelated documents
- the issue is format-level, not customer-specific
- the check has a low false-positive risk
- the fix improves tournament results without hurting speed or other adapters
- the behavior can be covered by a small synthetic fixture

Package-level work should follow this order:

1. Add a regression test that fails on the current behavior.
2. Add or update the smallest relevant QA check or hard gate.
3. Patch the converter, selector, scorer, or adapter.
4. Run the narrow test.
5. Run the full package test suite.
6. Update docs if behavior, setup, cost, or benchmark meaning changed.
7. Rerun the public benchmark smoke or a dated corpus benchmark when speed or
   quality claims changed.

## Gate, Check, Or Fix?

Use this decision table:

| If the issue means... | Add this |
|---|---|
| Output is unusable or unsafe to compare | Hard gate |
| Output is usable but lower quality | QA check |
| One project has a recurring weird document family | Project-local QA/in-house extension |
| Many users will hit the same issue | Package regression test and package fix |
| Only the source document proves the problem | LLM audit evidence plus a later deterministic check if possible |

Do not put every complaint into a hard gate. A hard gate says, "this candidate
must not win." Use that power carefully.

## Instructions For A Coding Agent

If you are a coding agent working on ADTM remediation, follow this checklist:

1. Read the `qa_report.json`, `remediation_plan.json`, and evidence packet.
2. Identify the smallest observable failure.
3. Decide whether the fix belongs in project-local hooks or package code.
4. Add a failing test or QA extension before changing converter behavior.
5. Make the smallest deterministic fix.
6. Rerun the exact failing case.
7. Rerun the narrow test.
8. Rerun the full package test suite for package changes.
9. Update docs if the issue class, behavior, or benchmark interpretation
   changed.
10. Do not delete the evidence. It is the case file.

Bad agent behavior:

- "I improved the converter" without a failing test.
- "The LLM said it is better" without deterministic evidence.
- "I fixed captions" by moving every italic line near the nearest image.
- "I made it pass" by disabling the check.

Good agent behavior:

- "Here is the failing fixture."
- "Here is the new check."
- "Here is the smallest fix."
- "Here is the before/after score."
- "Here is why this belongs locally or in the package."

## Instructions For A Human Reviewer

Ask five questions:

1. Is the reported issue real and material?
2. Is the evidence specific enough to reproduce it?
3. Does the test fail before the fix?
4. Does the fix preserve other document behavior?
5. Did speed, cost, or default-adapter policy change?

If the answer to any of those is unclear, do not merge the fix yet. Ask for a
smaller reproduction.

## What Success Looks Like

A good ADTM learning loop produces artifacts like this:

```text
winner/
  index.md
  qa_report.json
  remediation_plan.json

.any-doc-to-md/
  llm-findings/vendor-report-2026.json
  evidence-packets/vendor-report-2026.json
  qa-extensions/vendor-report-2026.py
  fix-extensions/vendor-report-2026.py

tests/
  test_output_qa_checks.py
  test_pdf_converter_caption_regression.py
```

At the end, the team can say:

```text
We found a conversion failure.
We preserved the evidence.
We made the failure executable as a test.
We fixed the converter or scoped a project-local hook.
We reran the tournament.
The next document benefits from the last document.
```

That is the difference between a converter and a conversion system.

## Intended Agent-In-Loop Design

This section records the original intended design so implementation stays
anchored to it.

The full learning loop is only active when a coding agent is running the
conversion. Standalone ADTM (no agent present) stops after step 3 and persists
findings for later review.

```text
1. Convert source file to Markdown via the inhouse adapter.
2. Run hard gates and QA checks to score conversion quality.
3. If quality is below threshold and a judge is configured:
     → ask the LLM judge what is wrong
     → save the judgement to .any-doc-to-md/llm-findings/
4. If a coding agent is present:
     a) Expand gates: add or update a qa-extension that catches this issue
        class deterministically in future runs.
     b) Expand fix coverage: add or update a fix-extension that fixes the issue
        for this document or document family across all adapters.
5. Re-run steps 1–4, up to 3 attempts total.
   If the same or more issues persist after 3 attempts:
     → stop retrying
     → escalate to a human with the full evidence trail
```

Key properties of this design:

- **Gate expansion (4a) is as important as the fix (4b).** A new gate makes the
  failure detectable on every future run. Without it, the fix is a guess that
  cannot be verified to hold.
- **The agent acts within the current run,** not as an offline follow-up step.
  Findings drive immediate implementation and re-test within the same session.
- **3-retry cap is a hard limit.** Some documents cannot be fixed
  programmatically. The cap prevents infinite loops and forces human review when
  automation cannot resolve the issue.
- **Human escalation is not failure.** It is the correct outcome when the
  problem exceeds what deterministic or agent-driven fixes can address.
- **Standalone ADTM is unaffected.** Without an agent, the loop produces
  findings and stub scaffolds and stops. The design does not require agent
  presence — it benefits from it.

## What Is Built vs What Is Planned

| Step | Status | Notes |
|---|---|---|
| 1. Convert → Markdown | ✅ implemented | tournament orchestrator, inhouse adapter |
| 2. Hard gates + QA score | ✅ implemented | `output_qa/hard_gates.py`, `output_qa/checks.py` |
| 3. LLM judge → save findings | ✅ implemented | `llm-findings/`, `remediation_plan.json` |
| 4a. Expand gate (working check) | 🔶 stub only | scaffold file generated but body is empty |
| 4b. Expand converter (working fix) | 🔶 stub only | scaffold file generated but body is empty |
| 5. Re-run up to 3× with fix applied | ✅ implemented | `learning_loop.run_learning_loop` retries with staged scaffolds applied |
| 5. Escalate to human after 3 failures | ✅ implemented | escalation record written to `.any-doc-to-md/escalations/{doc_key}.json` |

The gap between the current state and the intended design is not in the
structure — the scaffold files, findings persistence, and hook loading are all
present. The gap is that scaffolds are empty stubs rather than working
implementations, and the re-run loop does not yet apply agent-generated fixes
before retrying.

## Current Limits

- ADTM already has hard gates, QA checks, LLM audit, remediation plans,
  project-local QA hooks, project-local in-house hooks, and scaffold authoring.
- Scaffold files are generated as stubs. A coding agent must implement the
  check and fix bodies before they have any effect.
- The re-run loop retries with the next ranked candidate, not with an
  agent-generated fix applied to the same candidate.
- The agent-invocation bridge is intentionally explicit: `anydoc2md convert`
  writes findings and scaffold stubs, then stops. A coding agent reads
  `docs/agent-conversion-guide.md` and drives the retry loop via CLI calls.
  ADTM does not self-invoke agent sessions.

The safety boundary — no autonomous code mutation without review — is
deliberate and must be preserved as implementation catches up to the design.
