import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.auto_prd.gh_ops import should_stop_review_after_push
from tools.auto_prd import review_loop


class ShouldStopReviewAfterPushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path("/tmp/dummy")
        self.commit_sha = "abc123"

    def test_returns_true_when_all_conditions_met(self) -> None:
        def fake_run_cmd(cmd, **kwargs):
            self.assertEqual(cmd, ["git", "show", "-s", "--format=%cI", self.commit_sha])
            return ("2025-10-27T14:12:49Z\n", "", 0)

        graphql_responses = iter(
            [
                {
                    "data": {
                        "repository": {
                            "object": {
                                "statusCheckRollup": {
                                    "contexts": {
                                        "nodes": [
                                            {
                                                "__typename": "StatusContext",
                                                "context": "CodeRabbit",
                                                "state": "SUCCESS",
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    }
                },
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "issueComments": {
                                    "nodes": [
                                        {
                                            "author": {"login": "coderabbitai"},
                                            "createdAt": "2025-10-27T13:33:47Z",
                                        }
                                    ]
                                },
                                "reviews": {
                                    "nodes": [
                                        {
                                            "author": {"login": "copilot-pull-request-reviewer[bot]"},
                                            "submittedAt": "2025-10-27T14:14:05Z",
                                            "body": "Copilot reviewed 6 out of 6 changed files in this pull request and generated no new comments.",
                                        }
                                    ]
                                },
                            }
                        }
                    }
                },
            ]
        )

        def fake_graphql(query, variables):
            return next(graphql_responses)

        with mock.patch("tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd), mock.patch(
            "tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql
        ):
            should_stop = should_stop_review_after_push("owner/repo", 13, self.commit_sha, self.repo_root)

        self.assertTrue(should_stop)

    def test_returns_false_when_coderabbit_comments_after_commit(self) -> None:
        def fake_run_cmd(cmd, **kwargs):
            return ("2025-10-27T14:12:49Z", "", 0)

        graphql_responses = iter(
            [
                {
                    "data": {
                        "repository": {
                            "object": {
                                "statusCheckRollup": {
                                    "contexts": {
                                        "nodes": [
                                            {
                                                "__typename": "StatusContext",
                                                "context": "CodeRabbit",
                                                "state": "SUCCESS",
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    }
                },
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "issueComments": {
                                    "nodes": [
                                        {
                                            "author": {"login": "coderabbitai"},
                                            "createdAt": "2025-10-27T14:15:00Z",
                                        }
                                    ]
                                },
                                "reviews": {"nodes": []},
                            }
                        }
                    }
                },
            ]
        )

        def fake_graphql(query, variables):
            return next(graphql_responses)

        with mock.patch("tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd), mock.patch(
            "tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql
        ):
            should_stop = should_stop_review_after_push("owner/repo", 13, self.commit_sha, self.repo_root)

        self.assertFalse(should_stop)

    def test_returns_false_when_copilot_confirmation_missing(self) -> None:
        def fake_run_cmd(cmd, **kwargs):
            return ("2025-10-27T14:12:49Z", "", 0)

        graphql_responses = iter(
            [
                {
                    "data": {
                        "repository": {
                            "object": {
                                "statusCheckRollup": {
                                    "contexts": {
                                        "nodes": [
                                            {
                                                "__typename": "StatusContext",
                                                "context": "CodeRabbit",
                                                "state": "SUCCESS",
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    }
                },
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "issueComments": {"nodes": []},
                                "reviews": {
                                    "nodes": [
                                        {
                                            "author": {"login": "copilot-pull-request-reviewer[bot]"},
                                            "submittedAt": "2025-10-27T14:14:05Z",
                                            "body": "Copilot reviewed changes but found more to do.",
                                        }
                                    ]
                                },
                            }
                        }
                    }
                },
            ]
        )

        def fake_graphql(query, variables):
            return next(graphql_responses)

        with mock.patch("tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd), mock.patch(
            "tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql
        ):
            should_stop = should_stop_review_after_push("owner/repo", 13, self.commit_sha, self.repo_root)

        self.assertFalse(should_stop)


class ReviewFixLoopTests(unittest.TestCase):
    @mock.patch("tools.auto_prd.review_loop.should_stop_review_after_push", return_value=True)
    @mock.patch("tools.auto_prd.review_loop.get_unresolved_feedback", return_value=[])
    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    def test_loop_stops_when_exit_conditions_met(self, _mock_git_head, _mock_trigger, mock_get_unresolved, mock_should_stop) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            review_loop.review_fix_loop(
                pr_number=13,
                owner_repo="owner/repo",
                repo_root=Path(tmpdir),
                idle_grace=5,
                poll_interval=1,
                codex_model="gpt",
                allow_unsafe_execution=False,
                dry_run=False,
            )

        mock_get_unresolved.assert_called_once()
        mock_should_stop.assert_called()


if __name__ == "__main__":
    unittest.main()
