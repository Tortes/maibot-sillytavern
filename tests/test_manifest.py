from __future__ import annotations
import json
import unittest
from pathlib import Path


def version_tuple(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in value.split("."))


class ManifestTests(unittest.TestCase):
    def test_manifest_has_required_fields_and_covers_current_host_sdk(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / "_manifest.json").read_text(encoding="utf-8"))
        for key in (
            "manifest_version", "id", "version", "name", "description", "author",
            "license", "urls", "host_application", "sdk", "dependencies", "capabilities", "i18n",
        ):
            self.assertIn(key, manifest)
        self.assertEqual(manifest["manifest_version"], 2)
        self.assertTrue(manifest["author"]["url"].startswith("https://"))
        self.assertTrue(manifest["urls"]["repository"].startswith("https://"))
        self.assertLessEqual(version_tuple(manifest["host_application"]["min_version"]), version_tuple("1.3.19"))
        self.assertGreaterEqual(version_tuple(manifest["host_application"]["max_version"]), version_tuple("1.3.19"))
        self.assertLessEqual(version_tuple(manifest["sdk"]["min_version"]), version_tuple("2.21.0"))
        self.assertGreaterEqual(version_tuple(manifest["sdk"]["max_version"]), version_tuple("2.21.0"))


if __name__ == "__main__":
    unittest.main()
