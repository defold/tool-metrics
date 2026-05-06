import unittest

from scripts import generate_charts


class GenerateChartsTests(unittest.TestCase):
    def test_format_metric_uses_minutes_and_seconds_for_long_durations(self) -> None:
        self.assertEqual("10m 00s", generate_charts.format_metric(600000, "Milliseconds"))

    def test_format_metric_keeps_seconds_for_short_durations(self) -> None:
        self.assertEqual("12.35 s", generate_charts.format_metric(12345, "Milliseconds"))

    def test_value_axis_bounds_never_go_below_zero(self) -> None:
        self.assertEqual(0.0, generate_charts.value_axis_bounds([1234, 5678], "Milliseconds")[0])

    def test_value_axis_bounds_round_milliseconds_to_time_steps(self) -> None:
        self.assertEqual((0.0, 240000.0), generate_charts.value_axis_bounds([221665], "Milliseconds"))

    def test_value_axis_bounds_rounds_long_milliseconds_by_minutes(self) -> None:
        self.assertEqual((0.0, 1800000.0), generate_charts.value_axis_bounds([1457284], "Milliseconds"))

    def test_value_axis_bounds_round_bytes_in_display_units(self) -> None:
        self.assertEqual((0.0, 335544320.0), generate_charts.value_axis_bounds([313000000], "Bytes"))

    def test_value_axis_bounds_include_negative_byte_deltas(self) -> None:
        self.assertEqual((-1228800.0, 0.0), generate_charts.value_axis_bounds([-1048576], "Bytes"))

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
