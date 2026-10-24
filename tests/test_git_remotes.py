import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

SPEC = importlib.util.spec_from_file_location(
    "deploy_git_remotes", REPOSITORY / "bin/deploy-git-remotes.py"
)
assert SPEC is not None and SPEC.loader is not None
deploy_git_remotes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy_git_remotes)

from meta_project.walk import load_effective_metadata  # noqa: E402


class GitHubDerivationTest(unittest.TestCase):
    def test_common_github_url_forms(self) -> None:
        expected = ("kvn-dtrx", "example")
        self.assertEqual(
            deploy_git_remotes.github_owner_repo("https://github.com/kvn-dtrx/example"),
            expected,
        )
        self.assertEqual(
            deploy_git_remotes.github_owner_repo(
                "ssh://git@github.com/kvn-dtrx/example.git"
            ),
            expected,
        )
        self.assertEqual(
            deploy_git_remotes.github_owner_repo("git@github.com:kvn-dtrx/example.git"),
            expected,
        )

    def test_desired_remotes_use_https_and_preserve_repository(self) -> None:
        metadata = {
            "forges": {"github": {"url": "https://github.com/kvn-dtrx/example_project"}}
        }
        self.assertEqual(
            deploy_git_remotes.desired_remotes(metadata),
            {
                "origin": "https://github.com/kvn-dtrx/example_project.git",
                "mirror-glab": "https://gitlab.com/kvn-dtrx/example_project.git",
            },
        )

    def test_local_forge_overlay_takes_precedence(self) -> None:
        resolver = REPOSITORY.parent / "mtdt/src/wire/bin/resolve-mtdt.py"
        previous = os.environ.get("MTDT_RESOLVE_COMMAND")
        try:
            os.environ["MTDT_RESOLVE_COMMAND"] = str(resolver)
            with tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                (project / ".mtdt.yaml").write_text(
                    "forges:\n"
                    "  github:\n"
                    "    url: https://github.com/upstream/base-name\n",
                    encoding="utf-8",
                )
                (project / ".mtdt.local.yaml").write_text(
                    "forges:\n"
                    "  github:\n"
                    "    url: https://github.com/kvn-dtrx/fork-name\n",
                    encoding="utf-8",
                )
                metadata = load_effective_metadata(project)
        finally:
            if previous is None:
                os.environ.pop("MTDT_RESOLVE_COMMAND", None)
            else:
                os.environ["MTDT_RESOLVE_COMMAND"] = previous

        self.assertEqual(
            deploy_git_remotes.desired_remotes(metadata),
            {
                "origin": "https://github.com/kvn-dtrx/fork-name.git",
                "mirror-glab": "https://gitlab.com/kvn-dtrx/fork-name.git",
            },
        )

    def test_missing_github_forge_skips_all_managed_remotes(self) -> None:
        self.assertEqual(deploy_git_remotes.desired_remotes({}), {})

    def test_nas_remote_is_combined_with_forge_remotes(self) -> None:
        metadata = {
            "forges": {"github": {"url": "https://github.com/kvn-dtrx/example"}}
        }

        remotes = deploy_git_remotes.desired_remotes(
            metadata, fleet_url="ext::ssh nas upload-pack example.git"
        )

        self.assertEqual(remotes["nas"], "ext::ssh nas upload-pack example.git")
        self.assertIn("origin", remotes)
        self.assertIn("mirror-glab", remotes)

    def test_invalid_or_non_github_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            deploy_git_remotes.github_owner_repo("https://gitlab.com/kvn-dtrx/example")

    def test_unmanaged_ssh_forge_remote_keeps_identity(self) -> None:
        self.assertEqual(
            deploy_git_remotes.ssh_forge_to_https(
                "git@github.com:upstream/template_docs.git"
            ),
            "https://github.com/upstream/template_docs.git",
        )
        self.assertEqual(
            deploy_git_remotes.ssh_forge_to_https(
                "ssh://git@gitlab.com/group/subgroup/project.git"
            ),
            "https://gitlab.com/group/subgroup/project.git",
        )
        self.assertIsNone(
            deploy_git_remotes.ssh_forge_to_https(
                "https://github.com/kvn-dtrx/example.git"
            )
        )


if __name__ == "__main__":
    unittest.main()
