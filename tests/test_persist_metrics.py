import unittest

from scripts import persist_metrics


class PersistMetricsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
