#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


FIELDNAMES = [
    "commit_sha",
    "commit_time",
    "release_tag",
    "platform",
    "project",
    "install_size_bytes",
    "open_time_ms",
    "memory_after_open_bytes",
    "build_time_ms",
    "memory_after_build_bytes",
    "memory_added_by_build_bytes",
]
KEY_FIELDS = ["commit_sha", "commit_time", "release_tag", "platform", "project"]


def load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError(f"expected object in {path}")
    return data


def normalize_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return [{field: row.get(field, "") for field in FIELDNAMES} for row in reader]


def build_row(sample: dict[str, object], build_metadata: dict[str, object]) -> dict[str, str]:
    row = {
        "commit_sha": sample.get("commit_sha") or build_metadata.get("editor_commit_sha"),
        "commit_time": sample.get("commit_time") or sample.get("commit_date") or build_metadata.get("editor_commit_time"),
        "release_tag": sample.get("release_tag") or build_metadata.get("release_tag"),
        "platform": sample.get("platform") or build_metadata.get("platform"),
        "project": sample.get("project"),
        "install_size_bytes": sample.get("install_size_bytes"),
        "open_time_ms": sample.get("open_time_ms"),
        "memory_after_open_bytes": sample.get("memory_after_open_bytes"),
        "build_time_ms": sample.get("build_time_ms"),
        "memory_after_build_bytes": sample.get("memory_after_build_bytes"),
        "memory_added_by_build_bytes": sample.get("memory_added_by_build_bytes"),
    }
    missing = [field for field in KEY_FIELDS if not row[field]]
    if missing:
        raise RuntimeError(f"sample is missing required fields: {', '.join(missing)}")
    return {field: normalize_value(row[field]) for field in FIELDNAMES}


def row_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[field] for field in KEY_FIELDS)


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", required=True)
    parser.add_argument("--build-metadata", required=True)
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()

    sample = load_json(Path(args.sample))
    build_metadata = load_json(Path(args.build_metadata))
    csv_path = Path(args.csv)

    updated_row = build_row(sample, build_metadata)
    rows_by_key = {row_key(row): row for row in load_rows(csv_path)}
    rows_by_key[row_key(updated_row)] = updated_row
    rows = sorted(rows_by_key.values(), key=lambda row: (row["commit_time"], row["project"], row["platform"]))
    write_rows(csv_path, rows)
    print(f"wrote {len(rows)} rows to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
