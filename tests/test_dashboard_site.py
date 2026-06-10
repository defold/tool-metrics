from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
ASSET_ROOT = ROOT / "tool-metrics"


class DashboardSiteTests(unittest.TestCase):
    def test_root_index_references_site_assets_folder(self) -> None:
        html = (ROOT / "index.html").read_text()

        self.assertIn("https://cdn.plot.ly/plotly-2.35.2.min.js", html)
        self.assertIn('href="tool-metrics/css/dashboard.css"', html)
        self.assertIn('src="tool-metrics/js/dashboard.js"', html)
        self.assertIn('href="https://github.com/defold/tool-metrics"', html)
        self.assertIn('<option value="15" selected>Last 15</option>', html)

    def test_dashboard_fetches_root_metrics_csv(self) -> None:
        script = (ASSET_ROOT / "js" / "dashboard.js").read_text()

        self.assertIn('fetch("data/metrics.csv")', script)
        self.assertNotIn("analysis_index.json", script)

    def test_site_assets_stay_under_tool_metrics_folder(self) -> None:
        self.assertTrue((ROOT / "index.html").exists())
        self.assertTrue((ASSET_ROOT / "css" / "dashboard.css").exists())
        self.assertTrue((ASSET_ROOT / "js" / "dashboard.js").exists())
        self.assertFalse((ASSET_ROOT / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
