# Plan

## Goal
Collect nightly Ubuntu Defold editor metrics for the latest successful `dev` build, commit generated SVG charts to this repo, and show them in `README.md`.

## Scope
Track per Defold `dev` build:
- editor install size after download/unpack
- time to open project
- memory used after project open
- time to build the project
- additional memory used after build

## Development Strategy
1. Use `defold/sample-pixel-line-platformer` while developing the benchmark workflow for faster iteration.
2. Once signals and measurements are stable, switch the benchmark target to `defold/big-synthetic-project`.
3. Validate every milestone through GitHub Actions using a local `scripts/ci.py` driver inspired by https://github.com/vlaaad/shlice/blob/main/ci.py.
4. Iterate by pushing temporary snapshot branches through that driver instead of relying on ad hoc local execution.

## Build Source
1. Resolve the latest Defold alpha release that tracks `dev`.
2. Download the Ubuntu/Linux editor archive and unpack it.

## Measurement Strategy
### Open
- inspect logs for project-open completion markers
- also watch `.internal/editor.port` and the editor HTTP server as supporting signals

### Build
- trigger build via editor HTTP API
- use the blocking `/command/build` response as the build-finished signal
- inspect logs around the build to extract timing and memory details if available

### Memory
- prefer values emitted in editor logs if present and reliable
- otherwise sample process memory on Ubuntu as fallback

## Approach
1. Add a local `scripts/ci.py` helper that snapshots the current worktree to a temp branch, waits for a GitHub Actions run, streams status, and downloads artifacts.
2. Resolve the latest Defold alpha release and download the Linux editor artifact.
3. Download the benchmark project.
4. Launch the editor in GitHub Actions on Ubuntu and measure open duration and memory after open.
5. Trigger build through the editor HTTP API and measure build duration and memory delta after build.
6. Store each result as structured temporal data keyed by Defold commit metadata.
7. Generate SVG charts from the historical data using `commit_time` on the X axis.
8. Update `README.md` to embed the charts.
9. Commit changes back to the repo from the nightly workflow.

## Data Model
Store each sample with:
- `commit_sha`
- `commit_time`
- `release_tag`
- `platform`
- `project`
- `install_size_bytes`
- `open_time_ms`
- `memory_after_open_bytes`
- `build_time_ms`
- `memory_after_build_bytes`
- `memory_added_by_build_bytes`

Use `commit_time` as the canonical X-axis value for charts.

## Workflow Plan
1. Benchmark workflow:
    - runs on push to temp branches and on manual dispatch
    - benchmarks the editor
    - uploads raw logs and structured metrics as artifacts
    - is the primary target for validation through `scripts/ci.py`
2. Nightly workflow:
    - runs on schedule
    - benchmarks `big-synthetic-project`
    - appends metrics history
    - regenerates SVG charts
    - commits updated data/charts/README
    - should also be invokable through `scripts/ci.py` for pre-schedule validation

## Planned Files
- `.github/workflows/benchmark.yml`
- `.github/workflows/nightly.yml`
- `scripts/ci.py`
- `scripts/fetch_defold_build.*`
- `scripts/run_benchmark.*`
- `scripts/generate_charts.*`
- `data/metrics.csv`
- `charts/*.svg`
- `README.md`

## Notes
- Use a single fixed GitHub Actions runner OS: Ubuntu.
- Local iteration should use `scripts/ci.py`, which in turn uses `gh` to drive CI runs on temp branches instead of ad hoc local execution.
- The hardest part is identifying robust log-based open and memory signals.
- First implementation should focus on correctness, observability, and repeatability, then tighten timing and memory precision.

## Phase Plan
1. Phase 1: CI bootstrap ✅
   - add `scripts/ci.py` modeled after `shlice` so local validation always goes through GitHub Actions
   - add `.github/workflows/benchmark.yml` for Ubuntu, temp-branch pushes, and manual dispatch
   - resolve and download the latest Linux Defold editor and launch `sample-pixel-line-platformer`
   - upload raw logs and minimal metadata artifacts even on failure
   - validation: run `python scripts/ci.py` and confirm the workflow succeeds, the run URL is surfaced, and artifacts download locally
2. Phase 2: measurement stabilization ✅
   - detect reliable project-open completion markers from logs and supporting readiness signals
   - trigger builds through the editor HTTP API and measure build completion
   - extract memory values from logs when possible, otherwise sample the process on Ubuntu
   - emit one structured sample artifact per run
   - validation: iterate with `python scripts/ci.py` until downloaded artifacts show stable, repeatable open/build/memory measurements
3. Phase 3: persistence and charts ✅
   - append or dedupe samples in `data/metrics.csv` keyed by Defold commit metadata
   - generate SVG charts with `commit_time` on the X axis
   - update `README.md` to embed generated charts
   - validation: run `python scripts/ci.py` and verify downloaded artifacts contain updated metrics data and chart outputs generated in GitHub Actions
4. Phase 4: nightly automation
   - add `.github/workflows/nightly.yml` for scheduled execution
   - switch the benchmark target to `defold/big-synthetic-project` once signals are stable
   - benchmark, update history, regenerate charts, update `README.md`, and commit changes from the nightly workflow
   - validation: invoke the nightly path through `scripts/ci.py` before enabling or trusting the schedule, and verify reruns are idempotent

## First Milestones
1. Add `scripts/ci.py` and prove it can validate a temp-branch workflow run.
2. Prove Ubuntu editor launch in CI.
3. Collect and inspect logs for open/build markers and any memory reporting.
4. Wire blocking build through the editor HTTP API.
5. Record one sample for `sample-pixel-line-platformer`.
6. Swap the benchmark target to `big-synthetic-project`.
