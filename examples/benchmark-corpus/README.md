# ADTM Public Benchmark Corpus

This directory holds the small package-owned fixture set used by the public
benchmark reproduction guide.

Purpose:

- provide a stable, commit-owned benchmark smoke corpus
- exercise the default `inhouse` path on more than one source format
- keep release-facing benchmark examples free of private PRAI corpus paths

Current corpus members:

- `field-note.txt`
- `ops-brief.txt`
- `src/anydoc2md/probe_assets/probe_source_reference.pdf`

The PDF fixture lives under `probe_assets` because it is also used by the judge
probe flow. The benchmark reproduction guide treats it as part of the same
public fixture set.

This is not intended to be a representative ranking corpus. It is a compact,
package-owned benchmark smoke set that proves the benchmark pipeline, matrix
aggregation, and release docs remain runnable from a clean checkout.
