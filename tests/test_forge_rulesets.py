import importlib.util
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_forge_rulesets", REPOSITORY / "bin/check-forge-rulesets.py"
)
assert SPEC is not None and SPEC.loader is not None
check_forge_rulesets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_forge_rulesets)


class FakeApi:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, forge, method, endpoint, body=None):
        self.calls.append((forge, method, endpoint, body))
        response = self.responses.get((forge, method, endpoint))
        if callable(response):
            return response(body)
        return response


class CatalogueTest(unittest.TestCase):
    def test_repository_catalogue_is_valid(self) -> None:
        catalogue = check_forge_rulesets.load_catalog(
            REPOSITORY / "config/forge-rulesets.yaml"
        )
        self.assertEqual(catalogue["default-profile"], "protected-default")

    def test_invalid_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rules.yaml"
            path.write_text(
                "schema-version: 1\n"
                "default-profile: broken\n"
                "profiles:\n"
                "  broken:\n"
                "    managed-name: manual/name\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                check_forge_rulesets.load_catalog(path)


class MetadataSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogue = check_forge_rulesets.load_catalog(
            REPOSITORY / "config/forge-rulesets.yaml"
        )

    def test_gitlab_mirror_is_derived_from_github(self) -> None:
        metadata = {
            "forges": {"github": {"url": "https://github.com/kvn-dtrx/example.git"}}
        }
        self.assertEqual(
            check_forge_rulesets.forge_repository(metadata, "github"),
            "kvn-dtrx/example",
        )
        self.assertEqual(
            check_forge_rulesets.forge_repository(metadata, "gitlab"),
            "kvn-dtrx/example",
        )

    def test_explicit_nested_gitlab_project_wins(self) -> None:
        metadata = {
            "forges": {
                "github": {"url": "https://github.com/kvn-dtrx/example"},
                "gitlab": {"url": "https://gitlab.com/group/subgroup/different.git"},
            }
        }
        self.assertEqual(
            check_forge_rulesets.forge_repository(metadata, "gitlab"),
            "group/subgroup/different",
        )

    def test_github_opt_out_is_inherited_by_derived_gitlab(self) -> None:
        metadata = {
            "forges": {
                "github": {
                    "url": "https://github.com/kvn-dtrx/example",
                    "ruleset-profile": "none",
                }
            }
        }
        self.assertIsNone(
            check_forge_rulesets.selected_profile(metadata, "github", self.catalogue)
        )
        self.assertIsNone(
            check_forge_rulesets.selected_profile(metadata, "gitlab", self.catalogue)
        )


class GitHubAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        catalogue = check_forge_rulesets.load_catalog(
            REPOSITORY / "config/forge-rulesets.yaml"
        )
        self.profile = catalogue["profiles"][catalogue["default-profile"]]

    def test_payload_maps_all_shared_rules(self) -> None:
        payload = check_forge_rulesets.github_payload(self.profile)
        self.assertEqual(
            payload["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"]
        )
        self.assertEqual(
            {rule["type"] for rule in payload["rules"]},
            {
                "deletion",
                "non_fast_forward",
                "required_signatures",
                "required_linear_history",
            },
        )

    def test_missing_managed_ruleset_is_created_with_fix(self) -> None:
        endpoint = "repos/kvn-dtrx/example/rulesets"
        api = FakeApi({("github", "GET", endpoint): []})
        counts = check_forge_rulesets.reconcile_github(
            api, "kvn-dtrx/example", self.profile, True
        )
        self.assertEqual((counts.drift, counts.fixed), (1, 1))
        self.assertEqual(api.calls[-1][0:3], ("github", "POST", endpoint))

    def test_matching_managed_ruleset_has_no_drift(self) -> None:
        endpoint = "repos/kvn-dtrx/example/rulesets"
        detail_endpoint = f"{endpoint}/42"
        payload = check_forge_rulesets.github_payload(self.profile)
        api = FakeApi(
            {
                ("github", "GET", endpoint): [
                    {"id": 42, "name": self.profile["managed-name"]}
                ],
                ("github", "GET", detail_endpoint): payload,
            }
        )
        counts = check_forge_rulesets.reconcile_github(
            api, "kvn-dtrx/example", self.profile, False
        )
        self.assertEqual((counts.drift, counts.fixed), (0, 0))


class GitLabAdapterTest(unittest.TestCase):
    def test_fix_maps_supported_policy_and_reports_signature_gap(self) -> None:
        catalogue = check_forge_rulesets.load_catalog(
            REPOSITORY / "config/forge-rulesets.yaml"
        )
        profile = catalogue["profiles"][catalogue["default-profile"]]
        project = "projects/kvn-dtrx%2Fexample"
        protections = f"{project}/protected_branches?per_page=100"
        api = FakeApi(
            {
                ("gitlab", "GET", project): {
                    "default_branch": "main",
                    "merge_method": "merge",
                },
                ("gitlab", "GET", protections): [],
            }
        )
        counts = check_forge_rulesets.reconcile_gitlab(
            api, "kvn-dtrx/example", profile, True
        )
        self.assertEqual((counts.drift, counts.fixed, counts.errors), (2, 2, 1))
        mutations = {(call[1], call[2]) for call in api.calls if call[1] != "GET"}
        self.assertEqual(
            mutations,
            {
                ("POST", f"{project}/protected_branches"),
                ("PUT", project),
            },
        )
        self.assertFalse(any(call[2].endswith("/push_rule") for call in api.calls))


if __name__ == "__main__":
    unittest.main()
