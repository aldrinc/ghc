# Rebase Local Changes Audit - 2026-05-20

## Goal

Rebase `codex/paid-ads-qa-full-page-snapshot` onto `origin/main`, preserve real code changes, exclude local artifacts, and return a post-rebase commit decision queue.

## Plan

1. Snapshot the current dirty state before changing git state.
2. Create a code-only safety stash containing tracked edits and untracked real code under `mos/**`.
3. Rebase the branch onto `origin/main`.
4. Reapply the code-only stash and resolve blockers if they appear.
5. Audit the resulting worktree and classify code changes versus artifacts.
6. Produce the final decision queue with validation status.

## Acceptance

- Branch is no longer behind `origin/main`.
- Real code changes are present after rebase.
- Artifact directories are not intentionally staged or committed.
- `git diff --check` passes.
- Final report names blockers, if any.

## Verify Commands

- `git rev-list --left-right --count HEAD...origin/main`
- `git status --short --branch --untracked-files=no`
- `git diff --check`
