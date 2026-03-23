import unittest

from scripts import generate_charts


class GenerateChartsTests(unittest.TestCase):
    def test_render_chart_marks_failures_in_red(self) -> None:
        svg = generate_charts.render_chart(
            [
                {
                    "commit_time": "2026-03-23T12:00:00Z",
                    "status": "failed",
                    "error": "timed out waiting for build",
                    "open_time_ms": "",
                }
            ],
            "open_time_ms",
            "Open Time",
            "Milliseconds",
        )

        self.assertIn(generate_charts.FAILURE_COLOR, svg)
        self.assertIn("timed out waiting for build", svg)


if __name__ == "__main__":
    unittest.main()
