# Contributing

Thanks for helping improve `aprd`! Before opening a PR, please review these logging-specific guardrails:

- When touching logging, keep a single reader (`readLogsBatch`) that blocks for the first line and drains the remaining batch without returning `nil` due to timeouts.
- Do not close `logCh` in multiple places. The producer closes the channel after EOF; the consumer reads until it is closed.

Follow the repo’s README for build/test workflows and run `make ci` before submitting changes.
