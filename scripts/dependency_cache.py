#!/usr/bin/env python3
import argparse
import base64
from dataclasses import dataclass
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import threading
import urllib.parse
import urllib.request


KEY_PREFIX = "deps-v1-"
USER_AGENT = "editor-metrics/dependency-cache"
SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
DEPENDENCIES_RE = re.compile(r"^(\s*dependencies\s*=\s*)(.*)$")


@dataclass(frozen=True)
class CachedDependency:
    original_url: str
    archive_path: Path
    status: str


@dataclass(frozen=True)
class DependencyCacheResult:
    dependencies: list[str]
    cache_key: str | None
    cache_dir: Path | None
    archives: list[CachedDependency]
    hit_count: int
    download_count: int

    def metadata(self, server_base_url: str | None = None, local_urls: list[str] | None = None) -> dict[str, object]:
        entries = []
        for index, archive in enumerate(self.archives):
            entry = {
                "original_url": archive.original_url,
                "archive_path": str(archive.archive_path.resolve()),
                "status": archive.status,
            }
            if local_urls is not None:
                entry["local_url"] = local_urls[index]
            entries.append(entry)
        return {
            "enabled": bool(self.dependencies),
            "cache_key": self.cache_key,
            "cache_dir": None if self.cache_dir is None else str(self.cache_dir.resolve()),
            "dependency_count": len(self.dependencies),
            "hit_count": self.hit_count,
            "download_count": self.download_count,
            "server_base_url": server_base_url,
            "dependencies": entries,
        }


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


class DependencyArchiveServer:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.httpd: http.server.ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        handler = functools.partial(QuietHTTPRequestHandler, directory=str(self.cache_dir))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        if self.httpd is None:
            raise RuntimeError("dependency archive server is not started")
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    def local_url(self, archive_path: Path) -> str:
        name = urllib.parse.quote(archive_path.name)
        return f"{self.base_url}/{name}"

    def local_urls(self, archives: list[CachedDependency]) -> list[str]:
        return [self.local_url(archive.archive_path) for archive in archives]

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.thread is not None:
            self.thread.join(timeout=5)
            self.thread = None

    def __enter__(self) -> "DependencyArchiveServer":
        self.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.stop()


def normalized_dependencies(dependencies: list[str]) -> list[str]:
    return [dependency.strip() for dependency in dependencies if dependency.strip()]


def parse_game_project_dependencies(text: str) -> list[str]:
    section = None
    for line in text.splitlines():
        section_match = SECTION_RE.match(line.strip())
        if section_match:
            section = section_match.group(1).strip().lower()
            continue
        if section != "project":
            continue
        dependencies_match = DEPENDENCIES_RE.match(line)
        if dependencies_match:
            return normalized_dependencies(dependencies_match.group(2).split(","))
    return []


def dependency_cache_key(dependencies: list[str]) -> str:
    normalized = normalized_dependencies(dependencies)
    digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()
    return f"{KEY_PREFIX}{digest}"


def archive_filename(index: int, url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    basename = Path(parsed.path).name or f"dependency-{index}.zip"
    if not basename.endswith(".zip"):
        basename = f"{basename}.zip"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    safe_basename = re.sub(r"[^A-Za-z0-9._-]", "_", basename)
    return f"{index:02d}-{digest}-{safe_basename}"


def prepare_dependency_cache(game_project_path: Path, cache_root: Path, download_file) -> DependencyCacheResult:
    dependencies = parse_game_project_dependencies(game_project_path.read_text())
    if not dependencies:
        return DependencyCacheResult([], None, None, [], 0, 0)

    cache_key = dependency_cache_key(dependencies)
    cache_dir = cache_root / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)

    archives: list[CachedDependency] = []
    hit_count = 0
    download_count = 0
    for index, url in enumerate(dependencies):
        archive_path = cache_dir / archive_filename(index, url)
        if archive_path.is_file():
            hit_count += 1
            archives.append(CachedDependency(url, archive_path, "hit"))
            continue

        tmp_path = archive_path.with_name(f"{archive_path.name}.tmp")
        if tmp_path.exists():
            tmp_path.unlink()
        try:
            download_file(url, tmp_path)
            shutil.move(str(tmp_path), archive_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        download_count += 1
        archives.append(CachedDependency(url, archive_path, "downloaded"))

    return DependencyCacheResult(dependencies, cache_key, cache_dir, archives, hit_count, download_count)


def rewrite_game_project_dependencies_text(text: str, replacement_dependencies: list[str]) -> str:
    section = None
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        body = line[:-2] if line.endswith("\r\n") else line[:-1] if line.endswith("\n") else line
        ending = line[len(body):]
        section_match = SECTION_RE.match(body.strip())
        if section_match:
            section = section_match.group(1).strip().lower()
            continue
        if section != "project":
            continue
        dependencies_match = DEPENDENCIES_RE.match(body)
        if dependencies_match:
            lines[index] = f"{dependencies_match.group(1)}{','.join(replacement_dependencies)}{ending}"
            return "".join(lines)
    raise RuntimeError("could not find [project] dependencies setting in game.project")


def rewrite_game_project_dependencies(game_project_path: Path, replacement_dependencies: list[str]) -> None:
    game_project_path.write_text(
        rewrite_game_project_dependencies_text(game_project_path.read_text(), replacement_dependencies)
    )


def fetch_game_project_text(project: str, ref: str | None = None) -> str:
    if project.count("/") != 1:
        raise RuntimeError(f"project must be in owner/name form, got {project!r}")
    owner, name = project.split("/", 1)
    query = "" if ref is None else f"?ref={urllib.parse.quote(ref)}"
    url = f"https://api.github.com/repos/{owner}/{name}/contents/game.project{query}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
        raise RuntimeError(f"unexpected game.project response for {project}")
    return base64.b64decode(payload["content"]).decode("utf-8")


def emit_key(game_project_text: str) -> str:
    key = dependency_cache_key(parse_game_project_dependencies(game_project_text))
    line = f"key={key}"
    print(line, flush=True)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a") as output:
            output.write(line + "\n")
    return key


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    key_parser = subparsers.add_parser("key")
    source = key_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project")
    source.add_argument("--game-project")
    key_parser.add_argument("--ref")
    args = parser.parse_args()

    if args.command == "key":
        if args.game_project:
            game_project_text = Path(args.game_project).read_text()
        else:
            game_project_text = fetch_game_project_text(args.project, args.ref)
        emit_key(game_project_text)
        return 0

    raise RuntimeError(f"unsupported command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
