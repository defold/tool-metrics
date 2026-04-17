import unittest

from scripts import generate_charts


class GenerateChartsTests(unittest.TestCase):
    def test_format_metric_uses_minutes_and_seconds_for_long_durations(self) -> None:
        self.assertEqual("10m 00s", generate_charts.format_metric(600000, "Milliseconds"))

    def test_format_metric_keeps_seconds_for_short_durations(self) -> None:
        self.assertEqual("12.35 s", generate_charts.format_metric(12345, "Milliseconds"))

    def test_render_chart_marks_failures_in_red(self) -> None:
        svg = generate_charts.render_chart(
            [
                {
                    "commit_time": "2026-03-23T12:00:00Z",
                    "status": "failed",
                    "error": "timed out waiting for build",
                    "open_time_ms": "1234",
                }
            ],
            "open_time_ms",
            "Open Time",
            "Milliseconds",
        )

        self.assertIn(generate_charts.FAILURE_COLOR, svg)
        self.assertIn("timed out waiting for build", svg)
        self.assertEqual(1, svg.count("<circle "))

    def test_render_chart_does_not_mark_unrelated_metric_as_failure(self) -> None:
        svg = generate_charts.render_chart(
            [
                {
                    "commit_time": "2026-03-23T12:00:00Z",
                    "status": "failed",
                    "error": "timed out waiting for build",
                    "install_size_bytes": "1234",
                    "build_time_ms": "600000",
                }
            ],
            "install_size_bytes",
            "Install Size",
            "Bytes",
        )

        self.assertNotIn(generate_charts.FAILURE_COLOR, svg)
        self.assertNotIn("failed:", svg)

    def test_render_chart_draws_annotation_line_for_comment(self) -> None:
        svg = generate_charts.render_chart(
            [
                {
                    "commit_time": "2026-03-23T12:00:00Z",
                    "status": "ok",
                    "comment": "xcode-26.2",
                    "open_time_ms": "1234",
                },
                {
                    "commit_time": "2026-03-24T12:00:00Z",
                    "status": "ok",
                    "open_time_ms": "2345",
                },
            ],
            "open_time_ms",
            "Open Time",
            "Milliseconds",
        )

        self.assertIn("stroke-dasharray='6 6'", svg)
        self.assertIn("xcode-26.2", svg)


if __name__ == "__main__":
    unittest.main()
