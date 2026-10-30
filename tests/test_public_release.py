import tempfile
import unittest
from pathlib import Path

from release.audit_public import audit_tree


class PublicReleaseAuditTests(unittest.TestCase):
    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# SuperTeam\n", encoding="utf-8")
            (root / "ui" / "assets").mkdir(parents=True)
            (root / "ui" / "assets" / "superteam-circle.png").write_bytes(b"png")
            report = audit_tree(root)
            self.assertTrue(report["ok"], report)

    def test_runtime_and_machine_assets_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "api-connections.json").write_text(
                '{"key":"secret"}', encoding="utf-8"
            )
            (root / "ui" / "assets").mkdir(parents=True)
            (root / "ui" / "assets" / "installed-app-deadbeef.png").write_bytes(b"png")
            report = audit_tree(root)
            codes = {item["code"] for item in report["issues"]}
            self.assertIn("excluded-path", codes)
            self.assertIn("generated-app-icon", codes)

    def test_secret_and_absolute_user_path_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            credential = "ark-" + "example-secret"
            (root / "bad.txt").write_text(
                f"Authorization: Bearer {credential}\n"
                "C:\\Users\\Example\\Documents\\private.txt\n",
                encoding="utf-8",
            )
            report = audit_tree(root)
            codes = {item["code"] for item in report["issues"]}
            self.assertIn("credential-pattern", codes)
            self.assertIn("absolute-user-path", codes)

    def test_large_file_is_rejected_without_loading_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "oversize.bin"
            with path.open("wb") as handle:
                handle.truncate(50 * 1024 * 1024 + 1)
            report = audit_tree(root)
            self.assertIn("large-file", {item["code"] for item in report["issues"]})


if __name__ == "__main__":
    unittest.main()
