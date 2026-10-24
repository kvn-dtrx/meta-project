import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

SPEC = importlib.util.spec_from_file_location(
    "deploy_git_lfs_storage", REPOSITORY / "bin/deploy-git-lfs-storage.py"
)
assert SPEC is not None and SPEC.loader is not None
deploy_git_lfs_storage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy_git_lfs_storage)


class GitLfsStorageTest(unittest.TestCase):
    def test_lfs_declaration_is_repository_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            self.assertFalse(deploy_git_lfs_storage.declares_lfs(project))
            (project / ".gitattributes").write_text(
                "# comment\n/assets/*.zip filter=lfs diff=lfs merge=lfs -text\n",
                encoding="utf-8",
            )
            self.assertTrue(deploy_git_lfs_storage.declares_lfs(project))

    def test_storage_is_derived_from_data_root_and_forge_identity(self) -> None:
        metadata = {
            "forges": {"github": {"url": "https://github.com/kvn-dtrx/example.git"}}
        }
        self.assertEqual(
            deploy_git_lfs_storage.desired_storage(Path("/data"), metadata),
            Path("/data/resources/git-lfs/kvn-dtrx/example"),
        )

    def test_local_git_config_is_reconciled_without_repository_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            self.assertIsNone(deploy_git_lfs_storage.current_storage(project))
            wanted = Path("/data/resources/git-lfs/kvn-dtrx/example")
            deploy_git_lfs_storage.set_storage(project, wanted)
            self.assertEqual(
                deploy_git_lfs_storage.current_storage(project),
                str(wanted),
            )

    def test_author_and_project_storage_without_github(self) -> None:
        for forges in (
            None,
            {},
            {"github": {"url": None}},
            {"github": {"url": ""}},
            {"gitlab": {"url": "https://gitlab.com/example/notes"}},
        ):
            with self.subTest(forges=forges):
                metadata = {
                    "project": {"name": "Field Notes", "author": "Kvn Dtrx"},
                    "forges": forges,
                }
                self.assertEqual(
                    deploy_git_lfs_storage.desired_storage(Path("/data"), metadata),
                    Path("/data/resources/git-lfs/kvn-dtrx/field-notes"),
                )

    def test_authors_list_supplies_local_owner(self) -> None:
        metadata = {
            "project": {
                "name": "Field Notes",
                "authors": [{"name": "Kvn Dtrx"}],
            }
        }
        self.assertEqual(
            deploy_git_lfs_storage.desired_storage(Path("/data"), metadata),
            Path("/data/resources/git-lfs/kvn-dtrx/field-notes"),
        )

    def test_invalid_local_identity_is_rejected(self) -> None:
        projects = (
            None,
            {},
            {"name": "Field Notes"},
            {"name": "", "author": "Kvn Dtrx"},
            {"name": "Field Notes", "author": ""},
        )
        for project in projects:
            with self.subTest(project=project), self.assertRaises(ValueError):
                deploy_git_lfs_storage.desired_storage(
                    Path("/data"), {"project": project}
                )

    def test_invalid_github_url_does_not_silently_change_storage(self) -> None:
        with self.assertRaises(ValueError):
            deploy_git_lfs_storage.desired_storage(
                Path("/data"),
                {
                    "project": {"id": "496baa46-42e6-4fe0-b43c-ab62df71b984"},
                    "forges": {"github": {"url": "https://example.com/a/b"}},
                },
            )

    def test_missing_forge_identity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            deploy_git_lfs_storage.github_owner_repo({})


if __name__ == "__main__":
    unittest.main()
