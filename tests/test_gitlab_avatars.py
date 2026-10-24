import importlib.util
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "deploy_gitlab_avatars", REPOSITORY / "bin/deploy-gitlab-avatars.py"
)
assert SPEC is not None and SPEC.loader is not None
deploy_gitlab_avatars = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy_gitlab_avatars)


class GitLabTargetTest(unittest.TestCase):
    def test_mirror_glab_remote_defines_target_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(project),
                    "remote",
                    "add",
                    "mirror-glab",
                    "https://gitlab.com/group/subgroup/repo.git",
                ],
                check=True,
            )

            self.assertEqual(
                deploy_gitlab_avatars.gitlab_target(project),
                ("gitlab.com", "group/subgroup/repo"),
            )

    def test_gitlab_origin_is_used_as_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(project),
                    "remote",
                    "add",
                    "origin",
                    "git@gitlab.com:group/repo.git",
                ],
                check=True,
            )

            self.assertEqual(
                deploy_gitlab_avatars.gitlab_target(project),
                ("gitlab.com", "group/repo"),
            )

    def test_mirror_glab_rejects_another_forge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(project),
                    "remote",
                    "add",
                    "mirror-glab",
                    "https://example.com/group/repo.git",
                ],
                check=True,
            )

            with self.assertRaisesRegex(ValueError, "does not target gitlab.com"):
                deploy_gitlab_avatars.gitlab_target(project)


class ProjectLogoTest(unittest.TestCase):
    def test_accepts_repository_root_logo_png(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            logo = project / "logo.png"
            logo.write_bytes(deploy_gitlab_avatars.PNG_SIGNATURE + b"payload")

            self.assertEqual(deploy_gitlab_avatars.project_logo(project), logo)

    def test_rejects_oversized_logo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            logo = project / "logo.png"
            logo.write_bytes(
                deploy_gitlab_avatars.PNG_SIGNATURE
                + b"x" * (deploy_gitlab_avatars.MAX_AVATAR_BYTES + 1)
            )

            with self.assertRaisesRegex(ValueError, "at most 200 KiB"):
                deploy_gitlab_avatars.project_logo(project)


class AvatarUploadTest(unittest.TestCase):
    def test_upload_sends_multipart_body_through_glab(self) -> None:
        response = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"avatar_url":"https://gitlab.example/avatar.png"}',
            stderr="",
        )
        observed: dict[str, object] = {}

        def fake_run_glab(
            project_dir: Path, hostname: str, endpoint: str, *args: str
        ) -> subprocess.CompletedProcess[str]:
            body_index = args.index("--input") + 1
            observed["args"] = args
            observed["body"] = Path(args[body_index]).read_bytes()
            return response

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            logo = project / "logo.png"
            logo.write_bytes(deploy_gitlab_avatars.PNG_SIGNATURE + b"payload")
            with patch.object(
                deploy_gitlab_avatars, "run_glab", side_effect=fake_run_glab
            ):
                result = deploy_gitlab_avatars.upload_avatar(
                    project, "gitlab.example", "projects/group%2Frepo", logo
                )

        self.assertEqual(result, "https://gitlab.example/avatar.png")
        self.assertIn("--input", observed["args"])
        self.assertIn(b'name="avatar"; filename="logo.png"', observed["body"])
        self.assertIn(deploy_gitlab_avatars.PNG_SIGNATURE, observed["body"])

    def test_existing_avatar_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "logo.png").write_bytes(
                deploy_gitlab_avatars.PNG_SIGNATURE + b"payload"
            )
            with (
                patch.object(
                    deploy_gitlab_avatars,
                    "gitlab_target",
                    return_value=("gitlab.com", "group/repo"),
                ),
                patch.object(
                    deploy_gitlab_avatars,
                    "live_project",
                    return_value=(
                        {"avatar_url": "https://gitlab.com/current.png"},
                        "projects/group%2Frepo",
                    ),
                ),
                patch.object(deploy_gitlab_avatars, "upload_avatar") as upload,
                redirect_stdout(StringIO()),
            ):
                outcome = deploy_gitlab_avatars.sync_avatar(
                    project, check=False, force=False
                )

            self.assertEqual(outcome, "unchanged")
            upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
