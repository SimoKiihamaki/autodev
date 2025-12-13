import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase, main, mock

try:
    from tools.auto_prd import review_loop
    from tools.auto_prd.gh_ops import should_stop_review_after_push
except ImportError:
    from .. import review_loop
    from ..gh_ops import should_stop_review_after_push


class ShouldStopReviewAfterPushTests(TestCase):
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

        with (
            mock.patch("tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd),
            mock.patch("tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql),
        ):
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

        with (
            mock.patch("tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd),
            mock.patch("tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql),
        ):
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

        with (
            mock.patch("tools.auto_prd.gh_ops.run_cmd", side_effect=fake_run_cmd),
            mock.patch("tools.auto_prd.gh_ops.gh_graphql", side_effect=fake_graphql),
        ):
            should_stop = should_stop_review_after_push(
                "owner/repo", 13, self.commit_sha, self.repo_root
            )

        self.assertFalse(should_stop)


class ReviewFixLoopTests(TestCase):
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
    def test_timeout_expired_exception_increments_failure_counter(
        self,
        mock_policy_runner,
        _mock_git_head,
        _mock_trigger,
        _mock_acknowledge,
        _mock_should_stop,
        _mock_sleep,
    ) -> None:
        """Test that TimeoutExpired exception handling increments failure counter.

        This test exercises the error-handling path for TimeoutExpired exceptions
        by configuring mock_runner to immediately raise TimeoutExpired on every
        call. It does not test actual timeout behavior or real time delays; it
        only verifies the code responds correctly when such an exception occurs.
        """
        # Mock runner that always times out
        mock_runner = mock.MagicMock(
            side_effect=subprocess.TimeoutExpired(["claude"], 300)
        )
        mock_policy_runner.return_value = (mock_runner, "claude")

        # Return feedback so the loop tries to fix it
        with (
            mock.patch(
                "tools.auto_prd.review_loop.get_unresolved_feedback",
                return_value=[{"summary": "Fix this", "comment_id": 1}],
            ),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
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

        with (
            mock.patch(
                "tools.auto_prd.review_loop.get_unresolved_feedback",
                return_value=[{"summary": "Fix this", "comment_id": 1}],
            ),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
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
        "tools.auto_prd.review_loop.should_stop_review_after_push", return_value=False
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
        """Test that successful execution resets the failure counter.

        The scenario executes 4 runner calls in sequence to verify counter reset:

        1. First call FAILS -> counter becomes 1
        2. Second call SUCCEEDS -> counter resets to 0
        3. Third call FAILS -> counter becomes 1 (not 2, proving reset worked)
        4. Fourth call SUCCEEDS -> counter resets to 0, loop continues

        If the counter wasn't reset after call #2, call #3 would have set counter
        to 2, meaning we'd be closer to MAX_CONSECUTIVE_FAILURES=3.

        Exit path: After call #4 succeeds, the 5th get_unresolved_feedback call
        returns [] (empty list). With idle_grace=0, this triggers the exit condition
        at line 702-705 ("No unresolved feedback; stopping."). The mock for
        should_stop_review_after_push is set to False because that check (line 695)
        comes BEFORE the idle_grace check - we want to exercise the idle_grace path.
        """
        mock_runner = mock.MagicMock(
            side_effect=[
                subprocess.CalledProcessError(1, ["claude"], stderr=b"error"),
                ("output", ""),  # Success - should reset counter
                subprocess.CalledProcessError(1, ["claude"], stderr=b"error2"),
                ("output", ""),  # Success after reset - proves counter was reset
            ]
        )
        mock_policy_runner.return_value = (mock_runner, "claude")

        # Four feedback items to exercise the full sequence
        feedback_sequence = [
            [{"summary": "Fix this", "comment_id": 1}],  # -> fail
            [{"summary": "Fix this", "comment_id": 2}],  # -> success (reset)
            [{"summary": "Fix this", "comment_id": 3}],  # -> fail (counter=1, not 2)
            [{"summary": "Fix this", "comment_id": 4}],  # -> success
            [],  # Exit condition
        ]

        with (
            mock.patch(
                "tools.auto_prd.review_loop.get_unresolved_feedback",
                side_effect=feedback_sequence,
            ),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
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

        # Should return True since the loop completed normally (counter was reset)
        self.assertTrue(result)
        # Verify the runner was called exactly 4 times (2 failures + 2 successes)
        # If counter wasn't reset, we would have hit MAX_CONSECUTIVE_FAILURES and
        # returned False after 3 failures.
        self.assertEqual(
            mock_runner.call_count,
            4,
            "Expected 4 runner calls (fail, success, fail, success)",
        )

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

        with (
            mock.patch(
                "tools.auto_prd.review_loop.get_unresolved_feedback",
                return_value=[{"summary": "Fix this", "comment_id": 1}],
            ),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
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

        with (
            mock.patch(
                "tools.auto_prd.review_loop.get_unresolved_feedback",
                return_value=[{"summary": "Fix this", "comment_id": 1}],
            ),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
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

        with (
            mock.patch(
                "tools.auto_prd.review_loop.get_unresolved_feedback",
                return_value=[{"summary": "Fix this", "comment_id": 1}],
            ),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
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
        """Test that programming errors (AttributeError, TypeError, etc.) are re-raised.

        Note: KeyError is intentionally EXCLUDED from this test because it is treated
        as potentially recoverable. KeyError can occur from malformed API responses
        (transient) as well as programming bugs. See _PROGRAMMING_ERROR_TYPES for rationale.
        """
        for error_class in [AttributeError, TypeError, NameError]:
            with self.subTest(error_class=error_class):
                # Reset mock_policy_runner at start of each subTest for cleaner
                # isolation. While each iteration creates a fresh_runner, resetting
                # the parent mock prevents accumulation of call history.
                mock_policy_runner.reset_mock()

                # Create a specific error instance to verify identity preservation
                original_error = error_class("programming error")

                # Create fresh mock per error type for isolated call counts.
                fresh_runner = mock.MagicMock(side_effect=original_error)
                mock_policy_runner.return_value = (fresh_runner, "claude")

                with (
                    mock.patch(
                        "tools.auto_prd.review_loop.get_unresolved_feedback",
                        return_value=[{"summary": "Fix this", "comment_id": 1}],
                    ),
                    tempfile.TemporaryDirectory() as tmpdir,
                ):
                    raised_error = None
                    try:
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
                        self.fail(f"Expected {error_class.__name__} to be raised")
                    except error_class as e:
                        raised_error = e

                # Verify the SAME exception instance is re-raised unchanged
                self.assertIs(
                    raised_error,
                    original_error,
                    f"{error_class.__name__} should be re-raised unchanged, "
                    f"but got different instance: {raised_error!r}",
                )

                # Use assertEqual with msg as third arg for proper display
                self.assertEqual(
                    fresh_runner.call_count,
                    1,
                    f"{error_class.__name__} should not retry",
                )


if __name__ == "__main__":
    main()
