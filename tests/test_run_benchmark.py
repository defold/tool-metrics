import unittest
import subprocess
from pathlib import Path
from unittest import mock

from scripts import run_benchmark


class RunBenchmarkTests(unittest.TestCase):
    @mock.patch.dict("os.environ", {"BENCHMARK_PREFER_PATH_JCMD": "1"}, clear=True)
    @mock.patch("scripts.run_benchmark.shutil.which", return_value="/tmp/system-jcmd")
    def test_find_jcmd_executable_prefers_path_when_enabled(self, which_mock: mock.Mock) -> None:
        path = run_benchmark.find_jcmd_executable(Path("/tmp/defold"))

        self.assertEqual(Path("/tmp/system-jcmd"), path)
        which_mock.assert_called_once_with("jcmd")

    def test_parse_jcmd_heap_bytes_accepts_kibibytes(self) -> None:
        value = run_benchmark.parse_jcmd_heap_bytes("garbage-first heap total 2129920K, used 531072K")

        self.assertEqual(531072 * 1024, value)

    def test_parse_jcmd_heap_bytes_accepts_mebibytes(self) -> None:
        value = run_benchmark.parse_jcmd_heap_bytes("garbage-first heap total 2048M, used 122.5M")

        self.assertEqual(int(122.5 * 1024**2), value)

    def test_sample_memory_bytes_does_not_persist_ps_rss_fallback(self) -> None:
        with mock.patch("scripts.run_benchmark.jcmd_heap_bytes", return_value=None), mock.patch(
            "scripts.run_benchmark.process_tree_rss_bytes", return_value=987654321
        ), mock.patch("scripts.run_benchmark.log") as log_mock:
            value, source = run_benchmark.sample_memory_bytes(123, Path("/tmp/jcmd"))

        self.assertIsNone(value)
        self.assertEqual("jcmd_gc.heap_info_unavailable", source)
        self.assertTrue(any("process-tree rss=987654321 bytes" in call.args[0] for call in log_mock.call_args_list))

    def test_build_sample_can_record_open_timeout(self) -> None:
        sample = run_benchmark.build_sample(
            "defold/big-synthetic-project",
            {
                "editor_commit_sha": "abc",
                "editor_commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
            },
            123,
            open_time_ms=600000,
            status="failed",
            error="timed out waiting for project open",
        )

        self.assertEqual("failed", sample["status"])
        self.assertEqual(600000, sample["open_time_ms"])
        self.assertIsNone(sample["build_time_ms"])
        self.assertIsNone(sample["bob_build_time_ms"])

    def test_build_sample_can_record_build_timeout(self) -> None:
        sample = run_benchmark.build_sample(
            "defold/big-synthetic-project",
            {
                "editor_commit_sha": "abc",
                "editor_commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
            },
            123,
            open_result={"open_time_ms": 510000},
            build_time_ms=600000,
            status="failed",
            error="timed out waiting for build after 600000 ms",
        )

        self.assertEqual(510000, sample["open_time_ms"])
        self.assertEqual(600000, sample["build_time_ms"])
        self.assertEqual("failed", sample["status"])

    def test_build_sample_can_record_bob_build_time(self) -> None:
        sample = run_benchmark.build_sample(
            "defold/big-synthetic-project",
            {
                "editor_commit_sha": "abc",
                "editor_commit_time": "2026-03-23T12:00:00Z",
                "release_tag": "1.2.3-alpha",
                "platform": "macos-arm64",
            },
            123,
            bob_build_time_ms=456789,
        )

        self.assertEqual(456789, sample["bob_build_time_ms"])

    @mock.patch("scripts.run_benchmark.BUILD_HEARTBEAT_SECONDS", 1)
    def test_trigger_build_logs_heartbeat_while_waiting(self) -> None:
        started = mock.Mock()

        def slow_http_json(url: str, *, method: str = "GET", timeout: float = 10.0) -> tuple[int, object | None, str]:
            started()
            import time

            time.sleep(1.2)
            return 200, {"success": True}, ""

        with mock.patch("scripts.run_benchmark.http_json", side_effect=slow_http_json), mock.patch(
            "scripts.run_benchmark.log"
        ) as log_mock:
            result = run_benchmark.trigger_build(8080, 10)

        self.assertEqual({"success": True}, result["build_response"])
        self.assertTrue(started.called)
        self.assertTrue(any("waiting for build:" in call.args[0] for call in log_mock.call_args_list))

    @mock.patch("scripts.run_benchmark.time.monotonic", side_effect=[10.0, 12.345])
    def test_run_bob_build_resolves_before_measured_build(self, monotonic_mock: mock.Mock) -> None:
        with mock.patch(
            "scripts.run_benchmark.run_command",
            side_effect=[
                subprocess.CompletedProcess(["resolve"], 0, "resolved", ""),
                subprocess.CompletedProcess(["build"], 0, "built", ""),
            ],
        ) as run_command_mock, mock.patch("scripts.run_benchmark.write_text") as write_text_mock, mock.patch(
            "scripts.run_benchmark.shutil.rmtree"
        ) as rmtree_mock, mock.patch("pathlib.Path.exists", return_value=False), mock.patch("pathlib.Path.mkdir"):
            result = run_benchmark.run_bob_build(
                Path("/tmp/java"),
                Path("/tmp/defold.jar"),
                Path("/tmp/project"),
                Path("/tmp/project/.bob-output"),
                Path("/tmp/logs"),
                platform_name="macos-arm64",
                timeout_seconds=30,
            )

        self.assertEqual(2345, result["bob_build_time_ms"])
        self.assertEqual("resolve", run_command_mock.call_args_list[0].args[0][-1])
        self.assertEqual("build", run_command_mock.call_args_list[1].args[0][-1])
        self.assertEqual(".", run_command_mock.call_args_list[0].args[0][run_command_mock.call_args_list[0].args[0].index("--root") + 1])
        self.assertEqual(
            ".bob-output",
            run_command_mock.call_args_list[0].args[0][run_command_mock.call_args_list[0].args[0].index("--output") + 1],
        )
        self.assertFalse(rmtree_mock.called)
        self.assertEqual(4, write_text_mock.call_count)


if __name__ == "__main__":
    unittest.main()
