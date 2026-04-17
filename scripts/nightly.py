#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECT = "defold/big-synthetic-project"
DEFAULT_OPEN_TIMEOUT_SECONDS = 1800
DEFAULT_BUILD_TIMEOUT_SECONDS = 1800
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
README_PATH = ROOT / "README.md"
LAST_UPDATED_PREFIX = "Last updated: "


def run(*args: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        command = " ".join(args)
        message = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"{command}: {message}")
    return result


def log(message: str) -> None:
    print(f"[nightly] {message}", flush=True)


def run_logged(*args: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    log(f"running: {' '.join(args)}")
    process = subprocess.Popen(
        list(args),
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    output_lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        output_lines.append(line)
        print(line, end="", flush=True)
    process.stdout.close()
    returncode = process.wait()
    result = subprocess.CompletedProcess(list(args), returncode, "".join(output_lines), "")
    if check and returncode != 0:
        message = result.stdout.strip() or f"exit {returncode}"
        raise RuntimeError(f"{' '.join(args)}: {message}")
    log(f"finished: {' '.join(args)} (exit {returncode})")
    return result


def bool_arg(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got {value!r}")


def load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError(f"expected object in {path}")
    return data


def build_commit_message(sample: dict[str, object]) -> str:
    commit_sha = str(sample.get("commit_sha") or "").strip()
    short_sha = commit_sha[:12] if commit_sha else "latest-dev"
    return f"Update metrics for {short_sha}"


def build_persist_metrics_command(sample_path: Path, build_metadata_path: Path, metrics_csv: Path, comment: str) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "persist_metrics.py"),
        "--sample",
        str(sample_path),
        "--build-metadata",
        str(build_metadata_path),
        "--csv",
        str(metrics_csv),
    ]
    if comment.strip():
        command.extend(["--comment", comment.strip()])
    return command


def update_readme_last_updated(timestamp_utc: str, path: Path = README_PATH) -> None:
    marker = f"{LAST_UPDATED_PREFIX}`{timestamp_utc}`"
    lines = path.read_text().splitlines()
    for index, line in enumerate(lines):
        if line.startswith(LAST_UPDATED_PREFIX):
            lines[index] = marker
            path.write_text("\n".join(lines) + "\n")
            return

    insert_at = 3 if len(lines) >= 3 else len(lines)
    lines[insert_at:insert_at] = [marker, ""]
    path.write_text("\n".join(lines) + "\n")


def benchmark_outputs_changed() -> bool:
    return run("git", "diff", "--quiet", "--", "data/metrics.csv", "charts", check=False).returncode != 0


def commit_results(target_branch: str, sample: dict[str, object]) -> bool:
    run("git", "add", "--", "data/metrics.csv", "charts", "README.md")
    if run("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        print("no metrics changes to commit", flush=True)
        return False

    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", BOT_NAME)
    env.setdefault("GIT_AUTHOR_EMAIL", BOT_EMAIL)
    env.setdefault("GIT_COMMITTER_NAME", BOT_NAME)
    env.setdefault("GIT_COMMITTER_EMAIL", BOT_EMAIL)
    run("git", "commit", "-m", build_commit_message(sample), env=env)
    run("git", "push", "origin", f"HEAD:{target_branch}", env=env)
    print(f"pushed metrics update to {target_branch}", flush=True)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--metrics-csv", required=True)
    parser.add_argument("--charts-dir", required=True)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--editor-sha")
    parser.add_argument("--open-timeout-seconds", type=int, default=DEFAULT_OPEN_TIMEOUT_SECONDS)
    parser.add_argument("--build-timeout-seconds", type=int, default=DEFAULT_BUILD_TIMEOUT_SECONDS)
    parser.add_argument("--comment", default="")
    parser.add_argument("--commit", type=bool_arg, default=False)
    parser.add_argument("--target-branch")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    work_dir = Path(args.work_dir)
    artifacts_dir = Path(args.artifacts_dir)
    metrics_csv = Path(args.metrics_csv)
    charts_dir = Path(args.charts_dir)

    work_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    run_benchmark_command = [
        sys.executable,
        str(ROOT / "scripts" / "run_benchmark.py"),
        "--work-dir",
        str(work_dir),
        "--artifacts-dir",
        str(artifacts_dir),
        "--metadata-out",
        str(artifacts_dir / "run-metadata.json"),
        "--project",
        args.project,
        "--open-timeout-seconds",
        str(args.open_timeout_seconds),
        "--build-timeout-seconds",
        str(args.build_timeout_seconds),
    ]
    if args.editor_sha:
        run_benchmark_command.extend(["--editor-sha", args.editor_sha])
    log("starting nightly benchmark run")
    benchmark_result = run_logged(*run_benchmark_command, check=False)

    sample_path = artifacts_dir / "sample.json"
    build_metadata_path = artifacts_dir / "defold-build.json"
    if benchmark_result.returncode != 0 and (not sample_path.exists() or not build_metadata_path.exists()):
        command = " ".join(run_benchmark_command)
        raise RuntimeError(f"{command}: benchmark failed before producing sample artifacts")

    log("persisting benchmark sample into metrics history")
    run_logged(*build_persist_metrics_command(sample_path, build_metadata_path, metrics_csv, args.comment))
    log("regenerating charts from metrics history")
    run_logged(
        sys.executable,
        str(ROOT / "scripts" / "generate_charts.py"),
        "--metrics-csv",
        str(metrics_csv),
        "--charts-dir",
        str(charts_dir),
    )

    run_metadata = load_json(artifacts_dir / "run-metadata.json")
    if benchmark_outputs_changed():
        update_readme_last_updated(str(run_metadata["timestamp_utc"]))

    sample = load_json(sample_path)
    log(
        "sample result: "
        f"status={sample.get('status')} "
        f"commit_sha={sample.get('commit_sha')} "
        f"open_time_ms={sample.get('open_time_ms')} "
        f"build_time_ms={sample.get('build_time_ms')}"
    )
    if args.commit:
        target_branch = args.target_branch or os.environ.get("GITHUB_EVENT_REPOSITORY_DEFAULT_BRANCH") or "master"
        log(f"committing updated outputs to {target_branch}")
        commit_results(target_branch, sample)
    return benchmark_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
