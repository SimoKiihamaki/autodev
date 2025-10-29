import unittest
from unittest import mock

from tools.auto_prd.gh_ops import acknowledge_review_items, _format_review_reply_mention
from tools.auto_prd.constants import REVIEW_FALLBACK_MENTION


class FormatReviewReplyMentionTests(unittest.TestCase):
    def test_returns_fallback_for_empty_login(self) -> None:
        self.assertEqual(_format_review_reply_mention(""), REVIEW_FALLBACK_MENTION)

    def test_trims_whitespace(self) -> None:
        self.assertEqual(_format_review_reply_mention(" coderabbitai "), "@coderabbitai")

    def test_overrides_copilot_alias(self) -> None:
        self.assertEqual(
            _format_review_reply_mention("copilot"), "@copilot-pull-request-reviewer[bot]"
        )
        self.assertEqual(
            _format_review_reply_mention("Copilot"),
            "@copilot-pull-request-reviewer[bot]",
        )

    def test_preserves_known_bot_login(self) -> None:
        self.assertEqual(
            _format_review_reply_mention("copilot-pull-request-reviewer[bot]"),
            "@copilot-pull-request-reviewer[bot]",
        )

    def test_passthrough_for_regular_user(self) -> None:
        self.assertEqual(_format_review_reply_mention("CodeRabbitAI"), "@CodeRabbitAI")


class AcknowledgeReviewItemsTests(unittest.TestCase):
    def test_replies_with_safe_copilot_mention(self) -> None:
        processed: set[int] = set()
        items = [{"comment_id": 123, "thread_id": None, "author": "copilot"}]
        with mock.patch("tools.auto_prd.gh_ops.reply_to_review_comment") as mock_reply, mock.patch(
            "tools.auto_prd.gh_ops.resolve_review_thread"
        ):
            acknowledge_review_items("owner/repo", 5, items, processed)
        mock_reply.assert_called_once()
        args = mock_reply.call_args[0]
        self.assertEqual(args[0:3], ("owner", "repo", 5))
        self.assertEqual(args[3], 123)
        body = args[4]
        self.assertIn("@copilot-pull-request-reviewer[bot]", body)
        self.assertIn(123, processed)


if __name__ == "__main__":
    unittest.main()
