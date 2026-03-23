#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request


RELEASES_URL = "https://api.github.com/repos/defold/defold/releases?per_page=20"
COMMIT_URL = "https://api.github.com/repos/defold/defold/commits/{sha}"
ASSET_NAMES = {
    "macos-arm64": "Defold-arm64-macos.dmg",
}


def fetch_json(url: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "editor-metrics/phase-1",
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
    request = urllib.request.Request(url, headers={"User-Agent": "editor-metrics/phase-1"})
    with urllib.request.urlopen(request) as response, dest.open("wb") as output:
        shutil.copyfileobj(response, output)


def choose_release(releases: list[dict[str, object]]) -> dict[str, object]:
    for release in releases:
        if release.get("target_commitish") != "dev":
            continue
        if not release.get("prerelease"):
            continue
        tag = str(release.get("tag_name", ""))
        if "alpha" not in tag:
            continue
        return release
    raise RuntimeError("could not find alpha release tracking dev")


def editor_sha(body: str) -> str | None:
    match = re.search(r"Editor channel=.*? sha1: ([0-9a-f]{40})", body)
    return match.group(1) if match else None


def fetch_commit(commit_sha: str) -> dict[str, object]:
    commit = fetch_json(COMMIT_URL.format(sha=commit_sha))
    if not isinstance(commit, dict):
        raise RuntimeError(f"unexpected commit response for {commit_sha}")
    return commit


def mount_dmg(archive_path: Path) -> tuple[Path, str]:
    command = [
        "hdiutil",
        "attach",
        str(archive_path),
        "-nobrowse",
        "-readonly",
        "-plist",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=True)
    import plistlib

    plist = plistlib.loads(result.stdout.encode("utf-8"))
    entities = plist.get("system-entities", [])
    for entity in entities:
        mount_point = entity.get("mount-point")
        dev_entry = entity.get("dev-entry")
        if mount_point and dev_entry:
            return Path(mount_point), str(dev_entry)
    raise RuntimeError(f"could not determine mount point for {archive_path}")


def unmount_dmg(dev_entry: str) -> None:
    subprocess.run(["hdiutil", "detach", dev_entry], check=True, capture_output=True, text=True)


def unpack_archive(platform_name: str, archive_path: Path, unpack_dir: Path) -> None:
    if platform_name == "macos-arm64":
        mount_point, dev_entry = mount_dmg(archive_path)
        try:
            app_path = mount_point / "Defold.app"
            if not app_path.exists():
                raise RuntimeError(f"could not find Defold.app in {mount_point}")
            shutil.copytree(app_path, unpack_dir / "Defold.app", dirs_exist_ok=True)
        finally:
            unmount_dmg(dev_entry)
        return

    raise RuntimeError(f"unsupported platform {platform_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--metadata-out", required=True)
    parser.add_argument("--platform", default="macos-arm64")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    downloads_dir = work_dir / "downloads"
    unpack_dir = work_dir / "defold"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    unpack_dir.mkdir(parents=True, exist_ok=True)

    releases = fetch_json(RELEASES_URL)
    if not isinstance(releases, list):
        raise RuntimeError("unexpected GitHub releases response")
    release = choose_release(releases)
    asset_name = ASSET_NAMES.get(args.platform)
    if asset_name is None:
        raise RuntimeError(f"unsupported platform {args.platform}")

    asset = None
    for candidate in release.get("assets", []):
        if isinstance(candidate, dict) and candidate.get("name") == asset_name:
            asset = candidate
            break
    if asset is None:
        raise RuntimeError(f"could not find {asset_name} asset")

    archive_path = downloads_dir / asset_name
    download(str(asset["browser_download_url"]), archive_path)
    unpack_archive(args.platform, archive_path, unpack_dir)

    commit_sha = editor_sha(str(release.get("body", "")))
    commit = fetch_commit(commit_sha) if commit_sha else None

    metadata = {
        "release_tag": release.get("tag_name"),
        "release_name": release.get("name"),
        "release_url": release.get("html_url"),
        "release_published_at": release.get("published_at"),
        "platform": args.platform,
        "target_commitish": release.get("target_commitish"),
        "editor_commit_sha": commit_sha,
        "editor_commit_time": None if commit is None else commit.get("commit", {}).get("committer", {}).get("date"),
        "asset_name": asset.get("name"),
        "asset_url": asset.get("browser_download_url"),
        "asset_size_bytes": asset.get("size"),
        "asset_digest": asset.get("digest"),
        "archive_path": str(archive_path.resolve()),
        "unpack_dir": str(unpack_dir.resolve()),
    }
    metadata_out = Path(args.metadata_out)
    metadata_out.parent.mkdir(parents=True, exist_ok=True)
    metadata_out.write_text(json.dumps(metadata, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
