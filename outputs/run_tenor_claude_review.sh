#!/usr/bin/env bash
set -euo pipefail

cd /Users/aldrinclement/Documents/programming/marketi

unset ANTHROPIC_API_KEY
unset CLAUDE_API_KEY

RUN_ID="$(date +%Y%m%d%H%M%S)"
RAW_LOG_PATH="outputs/tenor-claude-deepseek-rerun-${RUN_ID}.jsonl"
TEXT_LOG_PATH="outputs/tenor-claude-deepseek-rerun-${RUN_ID}.log"

echo "Running Claude Code with model: deepseek-v4-pro"
echo "Working directory: $(pwd)"
echo "Prompt: outputs/tenor_copy_prompt.md"
echo "Review artifact: outputs/tenor-welcome-lead-nurturer-compressed-review.md"
echo "Raw stream log: ${RAW_LOG_PATH}"
echo "Readable log: ${TEXT_LOG_PATH}"
echo

claude --model deepseek-v4-pro --dangerously-skip-permissions --verbose --output-format stream-json -p "$(cat outputs/tenor_copy_prompt.md)" \
  | tee "${RAW_LOG_PATH}" \
  | node outputs/claude_stream_pretty.mjs \
  | tee "${TEXT_LOG_PATH}"

echo
echo "Done."
echo "Review artifact: outputs/tenor-welcome-lead-nurturer-compressed-review.md"
echo "Raw stream log: ${RAW_LOG_PATH}"
echo "Readable log: ${TEXT_LOG_PATH}"
echo
echo "----- REVIEW ARTIFACT START -----"
cat outputs/tenor-welcome-lead-nurturer-compressed-review.md
echo
echo "----- REVIEW ARTIFACT END -----"
