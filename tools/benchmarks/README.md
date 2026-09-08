# Docling comparison on OmniDocBench v1.6

Completed comparison: [100 equation-hard pages, 2026-09-09](results/20260909-equation-hard-100/REPORT.md),
with [machine-readable results](results/20260909-equation-hard-100/summary.json) and
the [fixed input manifest](results/20260909-equation-hard-100/manifest.json).
The user stopped the full queue and limited Paddle to100 pages. These scores
describe that shared subset; published full-dataset scores are separate references.

This experiment compares three local pipelines on the same 1,651 official page
images, using the pinned public OmniDocBench evaluator. It does not change the
Paper-Translation application or certify its parsing/release gates.

| Arm | Layout / recognition | Enabled features |
|---|---|---|
| `docling_enriched` | Docling 2.126.0 standard pipeline | Heron layout, EasyOCR Chinese+English full-page OCR, TableFormer accurate, CodeFormulaV2 formula+code enrichment |
| `docling_granite` | Docling VLM pipeline, IBM Granite Docling 258M | Whole-page DocTags recognition; separate standard-pipeline OCR/table/enrichment switches do not apply |
| `docling_paddle16` | Custom hybrid: Docling layout, EasyOCR cells, PaddleOCR-VL-1.6 region recognition | Docling supplies regions/order; Paddle recognizes text/code, tables and formulas with the corresponding official prompts |

The custom hybrid is **not** PaddleOCR's official end-to-end pipeline (including
its own layout detection and region refinement). Its measured score must not be
labelled as reproduction of the official PaddleOCR-VL-1.6 leaderboard score.
Neither inference pipeline uses ground-truth boxes, text, language or categories.
The separate preparation script uses annotations only to choose a smoke set and
create the official evaluation inputs; inference manifests contain image names
and checksums only.

All arms export tables as HTML to preserve merged cells for TEDS. Other content
uses Docling's Markdown serializer and predicted reading order. Pictures remain
placeholders; optional generated picture descriptions/classification are disabled
because they introduce content that is not a transcription target. Paddle code
regions use its official `OCR:` prompt; it has no dedicated code prompt.
HTML/underscore escaping is disabled consistently for text serialization so
recognized inline LaTeX is not changed into escaped prose. Table captions are
serialized once outside the table HTML. Raw recognition outputs are preserved.
Paddle table OTSL is decoded using the unmodified Apache-2.0 conversion functions
from PaddleX commit `c50f5da858020db473a2285f089bb8c7bbd6afdc`, vendored in
`paddle_otsl.py`; this includes Paddle's rectangular-grid normalization. No
ground-truth-dependent output repair or repetition removal is performed.

Data revision: `aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec`.
Evaluator commit: `193627ae9e97d89188468ed1ee3b7a856ff76044`.
Full model revisions and file hashes are recorded in `models.lock.json`.
Inference uses local model directories with Hugging Face offline mode enabled.

Run from the repository root (Python 3.12 for inference; the evaluator has its own
Python 3.10 Docker runtime):

```powershell
uv venv --python 3.12 .agent/local-data/venv-infer
uv pip install --python .agent/local-data/venv-infer/Scripts/python.exe 'docling[vlm,easyocr]==2.126.0'
uv pip install --python .agent/local-data/venv-infer/Scripts/python.exe --index-url https://download.pytorch.org/whl/cu130 'torch==2.14.0+cu130' 'torchvision==0.29.0+cu130'
.agent/local-data/venv-infer/Scripts/python.exe tools/benchmarks/prepare_docling.py --dataset
.agent/local-data/venv-infer/Scripts/python.exe tools/benchmarks/prepare_manifest.py --out .agent/tmp/RUN
.agent/local-data/venv-infer/Scripts/python.exe -m unittest tools.benchmarks.test_docling_compare
.agent/local-data/venv-infer/Scripts/python.exe tools/benchmarks/docling_compare.py --arm docling_enriched --manifest .agent/tmp/RUN/manifest.json --out .agent/tmp/RUN/docling_enriched
```

Repeat inference for the other arm names, sequentially on one GPU. Each arm
records effective options, package/model/script/manifest bindings, per-page
latency, allocated GPU memory, status and raw structured outputs. Model loading
on the first page is included in that page's latency; report cold and warm timing
separately. Paddle loading happens before per-page timing and must be disclosed
when discussing end-to-end startup time. GPU memory figures are allocated Torch
memory, not total system GPU memory.

Failed/empty predictions are retained as empty Markdown, never silently removed
from evaluation. Resume validates run bindings and output checksums. Changed
configuration or implementation requires a new run directory. A smoke result is
not a full benchmark result. Overall is only reported with a valid Formula CDM:
`((1 - Text Edit Distance) * 100 + Formula CDM + Table TEDS) / 3`.

Sources: [OmniDocBench](https://github.com/opendatalab/OmniDocBench),
[Granite Docling](https://huggingface.co/ibm-granite/granite-docling-258M),
[PaddleOCR-VL-1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6).
