import tempfile
import unittest
import urllib.request
from pathlib import Path

from scripts import dependency_cache


class DependencyCacheTests(unittest.TestCase):
    def test_extracts_project_dependencies(self) -> None:
        dependencies = dependency_cache.parse_game_project_dependencies(
            """
[library]
dependencies = https://example.com/ignored.zip

[project]
title = Test
dependencies = https://example.com/a.zip, https://example.com/b.zip
"""
        )

        self.assertEqual(["https://example.com/a.zip", "https://example.com/b.zip"], dependencies)

    def test_dependency_key_is_stable_for_whitespace_changes(self) -> None:
        first = dependency_cache.parse_game_project_dependencies(
            "[project]\ndependencies = https://example.com/a.zip, https://example.com/b.zip\n"
        )
        second = dependency_cache.parse_game_project_dependencies(
            "[project]\n  dependencies    =    https://example.com/a.zip ,https://example.com/b.zip  \n"
        )

        self.assertEqual(first, second)
        self.assertEqual(dependency_cache.dependency_cache_key(first), dependency_cache.dependency_cache_key(second))

    def test_dependency_key_changes_when_dependency_urls_change(self) -> None:
        first = dependency_cache.dependency_cache_key(["https://example.com/a.zip"])
        second = dependency_cache.dependency_cache_key(["https://example.com/b.zip"])

        self.assertNotEqual(first, second)

    def test_rewrite_replaces_only_project_dependencies(self) -> None:
        text = (
            "[library]\n"
            "dependencies = https://example.com/ignored.zip\n\n"
            "[project]\n"
            "title = Test\n"
            "dependencies = https://example.com/a.zip,https://example.com/b.zip\n\n"
            "[input]\n"
            "dependencies = /input/game.input_binding\n"
        )

        rewritten = dependency_cache.rewrite_game_project_dependencies_text(
            text,
            ["http://127.0.0.1:1234/a.zip", "http://127.0.0.1:1234/b.zip"],
        )

        self.assertIn("[library]\ndependencies = https://example.com/ignored.zip", rewritten)
        self.assertIn(
            "[project]\ntitle = Test\ndependencies = http://127.0.0.1:1234/a.zip,http://127.0.0.1:1234/b.zip",
            rewritten,
        )
        self.assertIn("[input]\ndependencies = /input/game.input_binding", rewritten)

    def test_prepare_cache_hit_avoids_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game_project = root / "game.project"
            game_project.write_text("[project]\ndependencies = https://example.com/a.zip\n")
            calls = []

            def download_file(url: str, dest: Path) -> None:
                calls.append(url)
                dest.write_bytes(b"archive")

            first = dependency_cache.prepare_dependency_cache(game_project, root / "cache", download_file)
            second = dependency_cache.prepare_dependency_cache(game_project, root / "cache", download_file)

        self.assertEqual(1, first.download_count)
        self.assertEqual(0, first.hit_count)
        self.assertEqual(0, second.download_count)
        self.assertEqual(1, second.hit_count)
        self.assertEqual(["https://example.com/a.zip"], calls)

    def test_local_server_serves_cached_archives_with_get_and_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            archive_path = cache_dir / "library.zip"
            archive_path.write_bytes(b"archive")
            server = dependency_cache.DependencyArchiveServer(cache_dir)
            server.start()
            try:
                url = server.local_url(archive_path)
                with urllib.request.urlopen(url) as response:
                    self.assertEqual(200, response.status)
                    self.assertEqual(b"archive", response.read())

                request = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(200, response.status)
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
