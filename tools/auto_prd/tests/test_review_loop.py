import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from tools.auto_prd.gh_ops import should_stop_review_after_push
    from tools.auto_prd import review_loop
except ImportError:
    from ..gh_ops import should_stop_review_after_push
    from .. import review_loop


class ShouldStopReviewAfterPushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path("/tmp/dummy")
        self.commit_sha = "abc123"

    def test_returns_true_when_all_conditions_met(self) -> None:
        def fake_run_cmd(cmd, **kwargs):
            self.assertEqual(
                cmd, ["git", "show", "-s", "--format=%cI", self.commit_sha]
            )
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
                                "comments": {
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
                                            "author": {
                                                "login": "copilot-pull-request-reviewer[bot]"
                                            },
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

        with mock.patch(
            "tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd
        ), mock.patch("tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql):
            should_stop = should_stop_review_after_push(
                "owner/repo", 13, self.commit_sha, self.repo_root
            )

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
                                "comments": {
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

        with mock.patch(
            "tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd
        ), mock.patch("tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql):
            should_stop = should_stop_review_after_push(
                "owner/repo", 13, self.commit_sha, self.repo_root
            )

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
                                "comments": {"nodes": []},
                                "reviews": {
                                    "nodes": [
                                        {
                                            "author": {
                                                "login": "copilot-pull-request-reviewer[bot]"
                                            },
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

        with mock.patch(
            "tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd
        ), mock.patch("tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql):
            should_stop = should_stop_review_after_push(
                "owner/repo", 13, self.commit_sha, self.repo_root
            )

        self.assertFalse(should_stop)


class ReviewFixLoopTests(unittest.TestCase):
    @mock.patch(
        "tools.auto_prd.review_loop.should_stop_review_after_push", return_value=True
    )
    @mock.patch("tools.auto_prd.review_loop.get_unresolved_feedback", return_value=[])
    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    def test_loop_stops_when_exit_conditions_met(
        self, _mock_git_head, _mock_trigger, mock_get_unresolved, mock_should_stop
    ) -> None:
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

    @mock.patch("tools.auto_prd.review_loop.time.sleep")
    @mock.patch(
        "tools.auto_prd.review_loop.should_stop_review_after_push", return_value=False
    )
    @mock.patch("tools.auto_prd.review_loop.acknowledge_review_items")
    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    @mock.patch("tools.auto_prd.review_loop.policy_runner")
    def test_timeout_increments_failure_counter(
        self,
        mock_policy_runner,
        _mock_git_head,
        _mock_trigger,
        _mock_acknowledge,
        _mock_should_stop,
        _mock_sleep,
    ) -> None:
        """Test that TimeoutExpired increments failure counter and returns False after max failures."""
        # Mock runner that always times out
        mock_runner = mock.MagicMock(
            side_effect=subprocess.TimeoutExpired(["claude"], 300)
        )
        mock_policy_runner.return_value = (mock_runner, "claude")

        # Return feedback so the loop tries to fix it
        with mock.patch(
            "tools.auto_prd.review_loop.get_unresolved_feedback",
            return_value=[{"summary": "Fix this", "comment_id": 1}],
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = review_loop.review_fix_loop(
                    pr_number=13,
                    owner_repo="owner/repo",
                    repo_root=Path(tmpdir),
                    idle_grace=0,
                    poll_interval=1,
                    codex_model="gpt",
                    allow_unsafe_execution=True,
                    dry_run=False,
                )

        # Should return False due to consecutive failures
        self.assertFalse(result)
        # Should have been called MAX_CONSECUTIVE_FAILURES times
        self.assertEqual(mock_runner.call_count, review_loop.MAX_CONSECUTIVE_FAILURES)

    @mock.patch("tools.auto_prd.review_loop.time.sleep")
    @mock.patch(
        "tools.auto_prd.review_loop.should_stop_review_after_push", return_value=False
    )
    @mock.patch("tools.auto_prd.review_loop.acknowledge_review_items")
    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    @mock.patch("tools.auto_prd.review_loop.policy_runner")
    def test_called_process_error_increments_failure_counter(
        self,
        mock_policy_runner,
        _mock_git_head,
        _mock_trigger,
        _mock_acknowledge,
        _mock_should_stop,
        _mock_sleep,
    ) -> None:
        """Test that CalledProcessError increments failure counter."""
        mock_runner = mock.MagicMock(
            side_effect=subprocess.CalledProcessError(1, ["claude"], stderr=b"error")
        )
        mock_policy_runner.return_value = (mock_runner, "claude")

        with mock.patch(
            "tools.auto_prd.review_loop.get_unresolved_feedback",
            return_value=[{"summary": "Fix this", "comment_id": 1}],
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = review_loop.review_fix_loop(
                    pr_number=13,
                    owner_repo="owner/repo",
                    repo_root=Path(tmpdir),
                    idle_grace=0,
                    poll_interval=1,
                    codex_model="gpt",
                    allow_unsafe_execution=True,
                    dry_run=False,
                )

        self.assertFalse(result)
        self.assertEqual(mock_runner.call_count, review_loop.MAX_CONSECUTIVE_FAILURES)

    @mock.patch("tools.auto_prd.review_loop.time.sleep")
    @mock.patch(
        "tools.auto_prd.review_loop.should_stop_review_after_push", return_value=True
    )
    @mock.patch("tools.auto_prd.review_loop.acknowledge_review_items")
    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    @mock.patch("tools.auto_prd.review_loop.policy_runner")
    def test_successful_execution_resets_failure_counter(
        self,
        mock_policy_runner,
        _mock_git_head,
        _mock_trigger,
        _mock_acknowledge,
        _mock_should_stop,
        _mock_sleep,
    ) -> None:
        """Test that successful execution resets the failure counter."""
        mock_runner = mock.MagicMock(
            side_effect=[
                subprocess.CalledProcessError(1, ["claude"], stderr=b"error"),
                ("output", ""),
            ]
        )
        mock_policy_runner.return_value = (mock_runner, "claude")

        feedback_sequence = [
            [{"summary": "Fix this", "comment_id": 1}],
            [{"summary": "Fix this", "comment_id": 2}],
            [],
        ]

        with mock.patch(
            "tools.auto_prd.review_loop.get_unresolved_feedback",
            side_effect=feedback_sequence,
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = review_loop.review_fix_loop(
                    pr_number=13,
                    owner_repo="owner/repo",
                    repo_root=Path(tmpdir),
                    idle_grace=0,
                    poll_interval=1,
                    codex_model="gpt",
                    allow_unsafe_execution=True,
                    dry_run=False,
                )

        # Should return True since the loop completed normally
        self.assertTrue(result)

    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    @mock.patch("tools.auto_prd.review_loop.policy_runner")
    def test_permission_error_reraises_immediately(
        self,
        mock_policy_runner,
        _mock_git_head,
        _mock_trigger,
    ) -> None:
        """Test that PermissionError is re-raised immediately without retry."""
        mock_runner = mock.MagicMock(
            side_effect=PermissionError("requires allow_unsafe_execution=True")
        )
        mock_policy_runner.return_value = (mock_runner, "claude")

        with mock.patch(
            "tools.auto_prd.review_loop.get_unresolved_feedback",
            return_value=[{"summary": "Fix this", "comment_id": 1}],
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaises(PermissionError):
                    review_loop.review_fix_loop(
                        pr_number=13,
                        owner_repo="owner/repo",
                        repo_root=Path(tmpdir),
                        idle_grace=0,
                        poll_interval=1,
                        codex_model="gpt",
                        allow_unsafe_execution=True,
                        dry_run=False,
                    )

        # Should only be called once - no retry on unrecoverable errors
        self.assertEqual(mock_runner.call_count, 1)

    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    @mock.patch("tools.auto_prd.review_loop.policy_runner")
    def test_file_not_found_error_reraises_immediately(
        self,
        mock_policy_runner,
        _mock_git_head,
        _mock_trigger,
    ) -> None:
        """Test that FileNotFoundError is re-raised immediately without retry."""
        mock_runner = mock.MagicMock(
            side_effect=FileNotFoundError("claude executable not found")
        )
        mock_policy_runner.return_value = (mock_runner, "claude")

        with mock.patch(
            "tools.auto_prd.review_loop.get_unresolved_feedback",
            return_value=[{"summary": "Fix this", "comment_id": 1}],
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaises(FileNotFoundError):
                    review_loop.review_fix_loop(
                        pr_number=13,
                        owner_repo="owner/repo",
                        repo_root=Path(tmpdir),
                        idle_grace=0,
                        poll_interval=1,
                        codex_model="gpt",
                        allow_unsafe_execution=True,
                        dry_run=False,
                    )

        self.assertEqual(mock_runner.call_count, 1)

    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    @mock.patch("tools.auto_prd.review_loop.policy_runner")
    def test_memory_error_reraises_immediately(
        self,
        mock_policy_runner,
        _mock_git_head,
        _mock_trigger,
    ) -> None:
        """Test that MemoryError is re-raised immediately without retry."""
        mock_runner = mock.MagicMock(side_effect=MemoryError("out of memory"))
        mock_policy_runner.return_value = (mock_runner, "claude")

        with mock.patch(
            "tools.auto_prd.review_loop.get_unresolved_feedback",
            return_value=[{"summary": "Fix this", "comment_id": 1}],
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaises(MemoryError):
                    review_loop.review_fix_loop(
                        pr_number=13,
                        owner_repo="owner/repo",
                        repo_root=Path(tmpdir),
                        idle_grace=0,
                        poll_interval=1,
                        codex_model="gpt",
                        allow_unsafe_execution=True,
                        dry_run=False,
                    )

        self.assertEqual(mock_runner.call_count, 1)

    @mock.patch("tools.auto_prd.review_loop.trigger_copilot")
    @mock.patch("tools.auto_prd.review_loop.git_head_sha", return_value="abc123")
    @mock.patch("tools.auto_prd.review_loop.policy_runner")
    def test_programming_errors_reraise_immediately(
        self,
        mock_policy_runner,
        _mock_git_head,
        _mock_trigger,
    ) -> None:
        """Test that programming errors (AttributeError, TypeError, etc.) are re-raised."""
        for error_class in [AttributeError, TypeError, NameError, KeyError]:
            with self.subTest(error_class=error_class):
                # Create fresh mock_runner per iteration. mock_policy_runner is reused
                # with reset state (reset_mock + new return_value) across iterations.
                mock_runner = mock.MagicMock(
                    side_effect=error_class("programming error")
                )
                mock_policy_runner.reset_mock()
                mock_policy_runner.return_value = (mock_runner, "claude")

                with mock.patch(
                    "tools.auto_prd.review_loop.get_unresolved_feedback",
                    return_value=[{"summary": "Fix this", "comment_id": 1}],
                ):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        with self.assertRaises(
                            error_class,
                            msg=f"{error_class.__name__} should be re-raised",
                        ):
                            review_loop.review_fix_loop(
                                pr_number=13,
                                owner_repo="owner/repo",
                                repo_root=Path(tmpdir),
                                idle_grace=0,
                                poll_interval=1,
                                codex_model="gpt",
                                allow_unsafe_execution=True,
                                dry_run=False,
                            )

                self.assertEqual(
                    mock_runner.call_count,
                    1,
                    f"{error_class.__name__} should not retry",
                )


if __name__ == "__main__":
    unittest.main()
