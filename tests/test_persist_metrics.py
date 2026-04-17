import unittest

from scripts import persist_metrics


class PersistMetricsTests(unittest.TestCase):
    def test_build_row_keeps_comment_from_cli(self) -> None:
        row = persist_metrics.build_row(
            {
                "project": "defold/big-synthetic-project",
            },
            {
                "editor_commit_sha": "abc",
                "editor_commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
            },
            "xcode-26.2",
        )

        self.assertEqual("xcode-26.2", row["comment"])

    def test_build_row_defaults_status_to_ok(self) -> None:
        row = persist_metrics.build_row(
            {
                "project": "defold/big-synthetic-project",
                "install_size_bytes": 1,
            },
            {
                "editor_commit_sha": "abc",
                "editor_commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
            },
        )

        self.assertEqual("ok", row["status"])
        self.assertEqual("", row["error"])
        self.assertEqual("", row["bob_build_time_ms"])

    def test_build_row_keeps_failed_status_and_error(self) -> None:
        row = persist_metrics.build_row(
            {
                "project": "defold/big-synthetic-project",
                "status": "failed",
                "error": "timed out waiting for build",
            },
            {
                "editor_commit_sha": "abc",
                "editor_commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
            },
        )

        self.assertEqual("failed", row["status"])
        self.assertEqual("timed out waiting for build", row["error"])

    def test_build_row_keeps_bob_build_time(self) -> None:
        row = persist_metrics.build_row(
            {
                "project": "defold/big-synthetic-project",
                "bob_build_time_ms": 123456,
            },
            {
                "editor_commit_sha": "abc",
                "editor_commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
            },
        )

        self.assertEqual("123456", row["bob_build_time_ms"])

    def test_merge_row_preserves_existing_comment_when_update_is_empty(self) -> None:
        merged = persist_metrics.merge_row(
            {
                "commit_sha": "abc",
                "commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
                "project": "defold/big-synthetic-project",
                "comment": "xcode-26.2",
                "status": "ok",
                "error": "",
                "install_size_bytes": "1",
                "bob_build_time_ms": "",
                "open_time_ms": "",
                "memory_after_open_bytes": "",
                "build_time_ms": "",
                "memory_after_build_bytes": "",
                "memory_added_by_build_bytes": "",
            },
            {
                "commit_sha": "abc",
                "commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
                "project": "defold/big-synthetic-project",
                "comment": "",
                "status": "ok",
                "error": "",
                "install_size_bytes": "2",
                "bob_build_time_ms": "",
                "open_time_ms": "",
                "memory_after_open_bytes": "",
                "build_time_ms": "",
                "memory_after_build_bytes": "",
                "memory_added_by_build_bytes": "",
            },
        )

        self.assertEqual("xcode-26.2", merged["comment"])
        self.assertEqual("2", merged["install_size_bytes"])


if __name__ == "__main__":
    unittest.main()
