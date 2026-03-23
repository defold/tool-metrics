#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECT = "defold/sample-pixel-line-platformer"
BENCHMARK_PLATFORM = "macos-arm64"
OPEN_TIMEOUT_SECONDS = 60
BUILD_TIMEOUT_SECONDS = 600
POLL_INTERVAL_SECONDS = 1.0
OPEN_LOG_MARKERS = {
    "project_loaded": "project loaded",
    "stage_loaded": "stage-loaded",
}
def run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="replace")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def write_json(path: Path, data: object) -> None:
    write_text(path, json.dumps(data, indent=2) + "\n")


def log(message: str) -> None:
    print(f"[run_benchmark] {message}", flush=True)


def capture_debug_state(artifacts_dir: Path) -> dict[str, object]:
    screenshot_path = artifacts_dir / "debug-screenshot.png"
    screenshot_result = run_command(["screencapture", "-x", str(screenshot_path)])
    processes_result = run_command(["osascript", "-e", 'tell application "System Events" to get name of every process'])
    frontmost_result = run_command(["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'])
    return {
        "screenshot_path": str(screenshot_path.resolve()) if screenshot_result.returncode == 0 and screenshot_path.exists() else None,
        "processes": processes_result.stdout.splitlines() if processes_result.returncode == 0 else [],
        "frontmost_process": frontmost_result.stdout.strip() if frontmost_result.returncode == 0 else None,
    }


def ensure_supported_host() -> None:
    if sys.platform != "darwin" or os.uname().machine != "arm64":
        raise RuntimeError(f"benchmark requires macOS arm64 host, got {sys.platform} {os.uname().machine}")


def find_editor_executable(unpack_dir: Path) -> Path:
    candidates = []
    for path in unpack_dir.rglob("*"):
        if path.is_file() and path.name == "Defold" and os.access(path, os.X_OK):
            candidates.append(path)
    if not candidates:
        raise RuntimeError("could not find Defold executable")
    candidates.sort(key=lambda path: len(path.parts))
    return candidates[0]


def find_jcmd_executable(unpack_dir: Path) -> Path:
    candidates = sorted(path for path in unpack_dir.rglob("jcmd") if path.is_file() and os.access(path, os.X_OK))
    if candidates:
        return candidates[0]
    jcmd_from_path = shutil.which("jcmd")
    if jcmd_from_path:
        return Path(jcmd_from_path)
    raise RuntimeError("could not find jcmd executable")


def editor_command(editor_executable: Path, project_dir: Path) -> list[str]:
    return [
        str(editor_executable),
        str((project_dir / "game.project").resolve()),
    ]


def fetch_json(url: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "editor-metrics/phase-2",
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "editor-metrics/phase-2"})
    with urllib.request.urlopen(request) as response, dest.open("wb") as output:
        shutil.copyfileobj(response, output)


def resolve_default_branch(project: str) -> str:
    if project.count("/") != 1:
        raise RuntimeError(f"project must be in owner/name form, got {project!r}")
    owner, name = project.split("/", 1)
    repo = fetch_json(f"https://api.github.com/repos/{owner}/{name}")
    if not isinstance(repo, dict):
        raise RuntimeError(f"unexpected repo response for {project}")
    branch = repo.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise RuntimeError(f"could not determine default branch for {project}")
    return branch


def project_archive_url(project: str, branch: str) -> str:
    owner, name = project.split("/", 1)
    return f"https://github.com/{owner}/{name}/archive/refs/heads/{branch}.zip"


def project_archive_name(project: str, branch: str) -> str:
    return project.replace("/", "-") + f"-{branch}.zip"


def download_project(projects_dir: Path, project: str) -> tuple[Path, str]:
    branch = resolve_default_branch(project)
    archive_path = projects_dir / project_archive_name(project, branch)
    download(project_archive_url(project, branch), archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        top_level_names = {
            Path(name).parts[0]
            for name in archive.namelist()
            if name and not name.startswith("__MACOSX/")
        }
        archive.extractall(projects_dir)
    directories = [projects_dir / name for name in sorted(top_level_names) if (projects_dir / name).is_dir()]
    if len(directories) != 1:
        raise RuntimeError(f"expected one extracted project directory, got {sorted(top_level_names)}")
    return directories[0], branch


def make_executable(path: Path) -> None:
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def child_pids(pid: int) -> list[int]:
    result = run_command(["ps", "-eo", "pid=,ppid="])
    if result.returncode != 0:
        return []
    children: dict[int, list[int]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        child_pid = int(parts[0])
        parent_pid = int(parts[1])
        children.setdefault(parent_pid, []).append(child_pid)

    queue = list(children.get(pid, []))
    descendants: list[int] = []
    while queue:
        child = queue.pop()
        descendants.append(child)
        queue.extend(children.get(child, []))
    return descendants


def process_tree_pids(root_pid: int) -> list[int]:
    pids = [root_pid]
    pids.extend(child_pids(root_pid))
    return [pid for pid in pids if process_exists(pid)]


def process_tree_rss_bytes(root_pid: int) -> int | None:
    pids = process_tree_pids(root_pid)
    if not pids:
        return None
    result = run_command(["ps", "-o", "pid=,rss=", "-p", ",".join(str(pid) for pid in pids)])
    if result.returncode != 0:
        return None
    total_kib = 0
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        total_kib += int(parts[1])
    return total_kib * 1024


def process_commands(root_pid: int) -> dict[int, str]:
    pids = process_tree_pids(root_pid)
    if not pids:
        return {}
    result = run_command(["ps", "-o", "pid=,command=", "-p", ",".join(str(pid) for pid in pids)])
    if result.returncode != 0:
        return {}
    commands: dict[int, str] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        commands[int(parts[0])] = parts[1]
    return commands


def java_process_pid(root_pid: int) -> int | None:
    commands = process_commands(root_pid)
    preferred = []
    for pid, command in commands.items():
        lowered = command.lower()
        if "com.defold.editor.main" in lowered:
            preferred.append(pid)
        elif "/java" in lowered or lowered.startswith("java "):
            preferred.append(pid)
    return preferred[-1] if preferred else None


def jcmd_heap_bytes(jcmd_executable: Path, root_pid: int) -> int | None:
    import re

    target_pid = java_process_pid(root_pid)
    if target_pid is None:
        return None
    gc_result = run_command([str(jcmd_executable), str(target_pid), "GC.run"])
    if gc_result.returncode != 0:
        return None
    result = run_command([str(jcmd_executable), str(target_pid), "GC.heap_info"])
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        match = re.search(r"\bused\s+(\d+)K\b", line)
        if match:
            return int(match.group(1)) * 1024
    return None


def directory_size_bytes(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def load_port(port_file: Path) -> int | None:
    if not port_file.exists():
        return None
    content = port_file.read_text().strip()
    if not content:
        return None
    try:
        return int(content)
    except ValueError:
        return None


def http_json(url: str, *, method: str = "GET", timeout: float = 10.0) -> tuple[int, object | None, str]:
    data = b"" if method == "POST" else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "User-Agent": "editor-metrics/phase-2",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body) if body else None
            return response.status, payload, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError:
            payload = None
        return exc.code, payload, body
    except urllib.error.URLError:
        return 0, None, ""


def socket_open(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except OSError:
            return False
    return True


def read_logs(log_paths: list[Path]) -> str:
    return "\n".join(read_text(path) for path in log_paths)


def tail_lines(path: Path, limit: int = 20) -> list[str]:
    lines = read_text(path).splitlines()
    return lines[-limit:]


def open_log_markers(log_paths: list[Path]) -> dict[str, bool]:
    logs = read_logs(log_paths).lower()
    return {name: marker in logs for name, marker in OPEN_LOG_MARKERS.items()}


def sample_memory_bytes(root_pid: int, jcmd_executable: Path) -> tuple[int | None, str]:
    from_jcmd = jcmd_heap_bytes(jcmd_executable, root_pid)
    if from_jcmd is not None:
        return from_jcmd, "jcmd_gc.heap_info"
    return None, "jcmd_gc.heap_info"


def wait_for_open(process: subprocess.Popen[str], project_dir: Path, log_paths: list[Path]) -> dict[str, object]:
    port_file = project_dir / ".internal" / "editor.port"
    start = time.monotonic()
    first_port_seen_ms: int | None = None
    first_socket_ready_ms: int | None = None
    first_http_ready_ms: int | None = None
    port: int | None = None
    last_report_second = -1

    while True:
        if process.poll() is not None:
            raise RuntimeError(f"editor exited before project opened (exit {process.returncode})")

        elapsed_ms = int((time.monotonic() - start) * 1000)
        if elapsed_ms > OPEN_TIMEOUT_SECONDS * 1000:
            raise RuntimeError(
                "timed out waiting for project open"
                f"; port_file={port_file.exists()}"
                f"; port={port}"
                f"; socket_ready={first_socket_ready_ms is not None}"
                f"; http_ready={first_http_ready_ms is not None}"
                f"; markers={json.dumps(open_log_markers(log_paths), sort_keys=True)}"
            )

        if port is None:
            port = load_port(port_file)
            if port is not None and first_port_seen_ms is None:
                first_port_seen_ms = elapsed_ms

        server_ready = False
        if port is not None:
            if first_socket_ready_ms is None and socket_open("127.0.0.1", port):
                first_socket_ready_ms = elapsed_ms
                log(f"editor socket accepted connections on port {port} after {elapsed_ms} ms")
            status, _payload, _body = http_json(f"http://127.0.0.1:{port}/command/build", timeout=2.0)
            if status in {200, 400, 404, 405}:
                server_ready = True
                if first_http_ready_ms is None:
                    first_http_ready_ms = elapsed_ms
                    log(f"editor HTTP server responded on port {port} after {elapsed_ms} ms")

        markers = open_log_markers(log_paths)
        current_second = elapsed_ms // 1000
        if current_second != last_report_second and current_second % 5 == 0:
            log(
                "waiting for open: "
                f"elapsed_ms={elapsed_ms} "
                f"port_file={port_file.exists()} "
                f"port={port} "
                f"socket_ready={first_socket_ready_ms is not None} "
                f"http_ready={first_http_ready_ms is not None} "
                f"markers={json.dumps(markers, sort_keys=True)}"
            )
            last_report_second = current_second
        if server_ready:
            return {
                "open_time_ms": elapsed_ms,
                "editor_port": port,
                "open_signals": {
                    "port_file": {
                        "path": str(port_file.resolve()),
                        "observed": first_port_seen_ms is not None,
                        "first_seen_ms": first_port_seen_ms,
                    },
                    "socket": {
                        "observed": first_socket_ready_ms is not None,
                        "first_seen_ms": first_socket_ready_ms,
                    },
                    "http_command_build": {
                        "observed": first_http_ready_ms is not None,
                        "first_seen_ms": first_http_ready_ms,
                    },
                    "log_markers": markers,
                },
            }

        time.sleep(POLL_INTERVAL_SECONDS)


def trigger_build(port: int) -> dict[str, object]:
    start = time.monotonic()
    status, payload, body = http_json(
        f"http://127.0.0.1:{port}/command/build",
        method="POST",
        timeout=BUILD_TIMEOUT_SECONDS,
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    if status != 200:
        raise RuntimeError(f"build failed with HTTP {status}: {body.strip() or 'empty response'}")
    if not isinstance(payload, dict):
        raise RuntimeError("build endpoint returned unexpected response")
    if not payload.get("success", False):
        raise RuntimeError(f"build reported failure: {json.dumps(payload)}")
    return {
        "build_time_ms": duration_ms,
        "build_response": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--metadata-out", required=True)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    artifacts_dir = Path(args.artifacts_dir)
    metadata_out = Path(args.metadata_out)
    logs_dir = artifacts_dir / "logs"
    work_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    ensure_supported_host()
    metadata: dict[str, object] = {
        "phase": "phase-3",
        "platform": BENCHMARK_PLATFORM,
        "project": args.project,
        "open_timeout_seconds": OPEN_TIMEOUT_SECONDS,
        "build_timeout_seconds": BUILD_TIMEOUT_SECONDS,
        "status": "failed",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    sample_path = artifacts_dir / "sample.json"

    editor_process: subprocess.Popen[str] | None = None
    editor_log = logs_dir / "editor.stdout.log"
    editor_err = logs_dir / "editor.stderr.log"
    launch_log = logs_dir / "launch.log"

    try:
        log(f"starting benchmark for project {args.project}")
        fetch_result = run_command(
            [
                sys.executable,
                str(ROOT / "scripts" / "fetch_defold_build.py"),
                "--work-dir",
                str(work_dir),
                "--metadata-out",
                str(artifacts_dir / "defold-build.json"),
                "--platform",
                BENCHMARK_PLATFORM,
            ]
        )
        write_text(logs_dir / "fetch.stdout.log", fetch_result.stdout)
        write_text(logs_dir / "fetch.stderr.log", fetch_result.stderr)
        log(f"fetch_defold_build.py exited with {fetch_result.returncode}")
        metadata["fetch_returncode"] = fetch_result.returncode
        if fetch_result.returncode != 0:
            raise RuntimeError("failed to fetch Defold build")

        build_metadata = json.loads((artifacts_dir / "defold-build.json").read_text())
        unpack_dir = Path(build_metadata["unpack_dir"])
        editor_executable = find_editor_executable(unpack_dir)
        jcmd_executable = find_jcmd_executable(unpack_dir)
        make_executable(editor_executable)
        if unpack_dir in jcmd_executable.parents:
            make_executable(jcmd_executable)
        log(f"using editor executable {editor_executable}")
        metadata["editor_executable"] = str(editor_executable.resolve())
        metadata["jcmd_executable"] = str(jcmd_executable.resolve())
        metadata["install_size_bytes"] = directory_size_bytes(unpack_dir)

        projects_dir = work_dir / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        project_dir, project_branch = download_project(projects_dir, args.project)
        log(f"downloaded project branch {project_branch} to {project_dir}")
        metadata["project_dir"] = str(project_dir.resolve())
        metadata["project_branch"] = project_branch

        write_text(launch_log, "using direct macOS launch\n")

        with editor_log.open("w") as stdout_handle, editor_err.open("w") as stderr_handle:
            env = os.environ.copy()
            env["LIBGL_ALWAYS_SOFTWARE"] = "1"
            env["_JAVA_OPTIONS"] = "-Dprism.order=sw -Dsun.java2d.opengl=false -Dsun.java2d.xrender=false -Ddefold.smoke.log=true"
            editor_process = subprocess.Popen(
                editor_command(editor_executable, project_dir),
                cwd=project_dir,
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                start_new_session=True,
            )
            log(f"started editor pid={editor_process.pid}")

            open_result = wait_for_open(editor_process, project_dir, [editor_log, editor_err])
            log(f"project open completed in {open_result['open_time_ms']} ms on port {open_result['editor_port']}")
            log("waiting 10 seconds before post-open heap measurement")
            time.sleep(10.0)
            memory_after_open_bytes, open_memory_source = sample_memory_bytes(editor_process.pid, jcmd_executable)
            log(f"memory after open: {memory_after_open_bytes} via {open_memory_source}")
            build_result = trigger_build(int(open_result["editor_port"]))
            log(f"build completed in {build_result['build_time_ms']} ms")
            memory_after_build_bytes, build_memory_source = sample_memory_bytes(editor_process.pid, jcmd_executable)
            log(f"memory after build: {memory_after_build_bytes} via {build_memory_source}")

        build_response = build_result["build_response"]
        issue_count = None
        if isinstance(build_response, dict) and isinstance(build_response.get("issues"), list):
            issue_count = len(build_response["issues"])

        sample = {
            "commit_sha": build_metadata.get("editor_commit_sha"),
            "commit_time": build_metadata.get("editor_commit_time"),
            "release_tag": build_metadata.get("release_tag"),
            "platform": build_metadata.get("platform", BENCHMARK_PLATFORM),
            "project": args.project,
            "install_size_bytes": metadata["install_size_bytes"],
            "open_time_ms": open_result["open_time_ms"],
            "memory_after_open_bytes": memory_after_open_bytes,
            "build_time_ms": build_result["build_time_ms"],
            "memory_after_build_bytes": memory_after_build_bytes,
            "memory_added_by_build_bytes": None
            if memory_after_open_bytes is None or memory_after_build_bytes is None
            else memory_after_build_bytes - memory_after_open_bytes,
        }
        write_json(sample_path, sample)

        metadata.update(
            {
                "status": "ok",
                "sample_path": str(sample_path.resolve()),
                "sample": sample,
                "open_signals": open_result["open_signals"],
                "editor_port": open_result["editor_port"],
                "memory_sources": {
                    "after_open": open_memory_source,
                    "after_build": build_memory_source,
                },
                "build_issue_count": issue_count,
            }
        )
        write_json(metadata_out, metadata)
        return 0
    except Exception as exc:
        log(f"benchmark failed: {exc}")
        metadata["error"] = str(exc)
        metadata["sample_path"] = str(sample_path.resolve())
        metadata["debug_tail"] = {
            "editor_stdout": tail_lines(editor_log),
            "editor_stderr": tail_lines(editor_err),
            "launch": tail_lines(launch_log),
        }
        metadata["debug_state"] = capture_debug_state(artifacts_dir)
        if sample_path.exists():
            metadata["sample"] = json.loads(sample_path.read_text())
        write_json(metadata_out, metadata)
        raise
    finally:
        if editor_process is not None:
            try:
                os.killpg(editor_process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                terminate_process(editor_process)
            else:
                try:
                    editor_process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(editor_process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    editor_process.wait(timeout=15)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
