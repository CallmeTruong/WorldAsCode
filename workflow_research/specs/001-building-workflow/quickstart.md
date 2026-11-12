# Quickstart

From `D:\WorldAsCode\workflow_research` in PowerShell:
```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e '.[test]'
npm ci
.venv/Scripts/python -m playwright install chromium
.venv/Scripts/python -m building_workflow.cli doctor
.venv/Scripts/python -m building_workflow.cli samples
.venv/Scripts/python -m building_workflow.cli run --sample rietveld --strategy spec --max-refinements 1
.venv/Scripts/python -m building_workflow.cli report
.venv/Scripts/python -m pytest -q
```
The existing `../.env` supplies gateway credentials and model; no secret copying is required. Optional `WORKFLOW_MODEL`, `WORKFLOW_VISION_MODEL`, `WORKFLOW_CODE_MODEL`, `WORKFLOW_REVIEW_MODEL`, `WORKFLOW_INPUT_USD_PER_MILLION`, `WORKFLOW_OUTPUT_USD_PER_MILLION` override defaults. API capability must support image messages and JSON output.

Open `reports/index.html` and each linked run's `index.html`. Inspect reference vs baseline/refinement and all standard views. Expect partial/failed rather than high-fidelity certification; unobserved geometry is inferred. Monetary costs show unknown unless explicit rates exist. See [CLI contract](contracts/cli.md) and [data model](data-model.md).

Upstream checkout: `git clone https://github.com/img2threejs/img2threejs.git vendor/img2threejs`, then `git -C vendor/img2threejs checkout 0c0c49bc168e648dbaf9c8c080474de0b3a941b6`. Source snapshots and exact installed dependencies are recorded in run manifests/lock files.
