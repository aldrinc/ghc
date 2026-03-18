#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

API_BASE_URL = "https://api.github.com"


@dataclass
class WorkflowSummary:
    name: str
    event: str | None
    status: str | None
    conclusion: str | None
    html_url: str | None
    run_id: int | None
    head_branch: str | None
    created_at: str | None
    jobs: list[dict[str, str | None]]


def run_git(args: list[str], cwd: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def resolve_repo(cwd: str, explicit_repo: str | None) -> str:
    if explicit_repo:
        return explicit_repo
    remote_url = run_git(["remote", "get-url", "origin"], cwd)
    for prefix in ("https://github.com/", "git@github.com:"):
        if remote_url.startswith(prefix):
            repo = remote_url[len(prefix) :]
            if repo.endswith(".git"):
                repo = repo[:-4]
            return repo
    raise SystemExit(f"Unsupported origin remote for GitHub API lookup: {remote_url}")


def resolve_sha(cwd: str, ref: str) -> str:
    return run_git(["rev-parse", ref], cwd)


def resolve_branch(cwd: str, ref: str) -> str | None:
    branch = run_git(["rev-parse", "--abbrev-ref", ref], cwd)
    if branch == "HEAD":
        return None
    return branch


def resolve_auth_headers(cwd: str) -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}

    try:
        credential_blob = subprocess.check_output(
            ["git", "credential", "fill"],
            cwd=cwd,
            input="protocol=https\nhost=github.com\n\n",
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    fields = {}
    for line in credential_blob.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()

    username = fields.get("username")
    password = fields.get("password")
    if not username or not password:
        return {}

    basic_token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {basic_token}"}


def github_get(path: str, auth_headers: dict[str, str]) -> Any:
    request = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            **auth_headers,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed for {path}: HTTP {exc.code}: {body}") from exc


def fetch_workflow_runs(repo: str, sha: str, auth_headers: dict[str, str]) -> list[dict[str, Any]]:
    encoded_repo = urllib.parse.quote(repo, safe="/")
    encoded_sha = urllib.parse.quote(sha, safe="")
    payload = github_get(f"/repos/{encoded_repo}/actions/runs?head_sha={encoded_sha}&per_page=50", auth_headers)
    return payload.get("workflow_runs", [])


def fetch_jobs(repo: str, run_id: int, auth_headers: dict[str, str]) -> list[dict[str, Any]]:
    encoded_repo = urllib.parse.quote(repo, safe="/")
    payload = github_get(f"/repos/{encoded_repo}/actions/runs/{run_id}/jobs", auth_headers)
    return payload.get("jobs", [])


def latest_run(
    runs: list[dict[str, Any]],
    workflow_name: str,
    *,
    branch: str | None,
    allowed_events: set[str] | None,
) -> dict[str, Any] | None:
    candidates = []
    for run in runs:
        if run.get("name") != workflow_name:
            continue
        if branch and run.get("head_branch") != branch:
            continue
        if allowed_events and run.get("event") not in allowed_events:
            continue
        candidates.append(run)
    candidates.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or 0), reverse=True)
    return candidates[0] if candidates else None


def summarize_run(repo: str, run: dict[str, Any] | None, auth_headers: dict[str, str]) -> WorkflowSummary | None:
    if run is None:
        return None
    jobs_payload = fetch_jobs(repo, int(run["id"]), auth_headers) if run.get("id") is not None else []
    jobs = [
        {
            "name": job.get("name"),
            "status": job.get("status"),
            "conclusion": job.get("conclusion"),
            "html_url": job.get("html_url"),
        }
        for job in jobs_payload
    ]
    return WorkflowSummary(
        name=run.get("name"),
        event=run.get("event"),
        status=run.get("status"),
        conclusion=run.get("conclusion"),
        html_url=run.get("html_url"),
        run_id=run.get("id"),
        head_branch=run.get("head_branch"),
        created_at=run.get("created_at"),
        jobs=jobs,
    )


def overall_state(
    ci_cd: WorkflowSummary | None,
    self_deploy: WorkflowSummary | None,
    *,
    expect_production: bool,
) -> tuple[str, str]:
    if ci_cd is None:
        return "pending", "No CI/CD run has been created for this commit yet."
    if ci_cd.status != "completed":
        return "pending", f"CI/CD is still {ci_cd.status}."
    if ci_cd.conclusion != "success":
        failed_jobs = [job["name"] for job in ci_cd.jobs if job.get("conclusion") == "failure"]
        detail = f" Failed jobs: {', '.join(failed_jobs)}." if failed_jobs else ""
        return "failure", f"CI/CD concluded with {ci_cd.conclusion}.{detail}"

    deploy_job = next((job for job in ci_cd.jobs if job.get("name") == "deploy"), None)
    if expect_production:
        if ci_cd.event == "workflow_dispatch":
            if deploy_job is None:
                return "incomplete", "CI/CD succeeded but no deploy job was recorded."
            if deploy_job.get("status") != "completed":
                return "pending", f"CI/CD deploy job is still {deploy_job.get('status')}."
            if deploy_job.get("conclusion") != "success":
                return "incomplete", f"CI/CD deploy job concluded with {deploy_job.get('conclusion')}."
            return "success", "CI/CD and the manual production deploy job both completed successfully."

        if self_deploy is None:
            return "pending", "CI/CD succeeded; waiting for Self Deploy to start."
        if self_deploy.status != "completed":
            return "pending", f"Self Deploy is still {self_deploy.status}."
        if self_deploy.conclusion != "success":
            return "failure", f"Self Deploy concluded with {self_deploy.conclusion}."

        apply_job = next((job for job in self_deploy.jobs if job.get("name") == "apply"), None)
        if apply_job is None:
            return "incomplete", "Self Deploy succeeded but no apply job was recorded."
        if apply_job.get("status") != "completed":
            return "pending", f"Self Deploy apply job is still {apply_job.get('status')}."
        if apply_job.get("conclusion") != "success":
            return "incomplete", f"Self Deploy apply job concluded with {apply_job.get('conclusion')}."
        return "success", "CI/CD and Self Deploy both completed successfully."

    if self_deploy is not None:
        if self_deploy.status != "completed":
            return "pending", f"Self Deploy is still {self_deploy.status}."
        if self_deploy.conclusion != "success":
            return "failure", f"Self Deploy concluded with {self_deploy.conclusion}."

    return "success", "CI/CD completed successfully."


def print_summary(
    repo: str,
    sha: str,
    ci_cd: WorkflowSummary | None,
    self_deploy: WorkflowSummary | None,
    state: str,
    message: str,
    *,
    json_output: bool,
) -> None:
    payload = {
        "repo": repo,
        "sha": sha,
        "overall_state": state,
        "message": message,
        "ci_cd": asdict(ci_cd) if ci_cd else None,
        "self_deploy": asdict(self_deploy) if self_deploy else None,
    }
    if json_output:
        print(json.dumps(payload, indent=2))
        return

    print(f"repo: {repo}")
    print(f"sha: {sha}")
    print(f"overall_state: {state}")
    print(f"message: {message}")
    for label, summary in (("ci_cd", ci_cd), ("self_deploy", self_deploy)):
        if summary is None:
            print(f"{label}: missing")
            continue
        print(
            f"{label}: status={summary.status} conclusion={summary.conclusion} "
            f"event={summary.event} branch={summary.head_branch} url={summary.html_url}"
        )
        for job in summary.jobs:
            print(
                "  "
                f"job={job.get('name')} status={job.get('status')} "
                f"conclusion={job.get('conclusion')} url={job.get('html_url')}"
            )


def state_exit_code(state: str) -> int:
    return {
        "success": 0,
        "failure": 1,
        "incomplete": 2,
        "pending": 3,
    }[state]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize GitHub Actions status for a commit and optionally wait until the push is fully resolved."
        )
    )
    parser.add_argument("--repo", help="GitHub repo in owner/name format. Defaults to origin remote.")
    parser.add_argument("--sha", default="HEAD", help="Git ref or SHA to inspect. Defaults to HEAD.")
    parser.add_argument(
        "--branch",
        help="Expected branch for workflow runs. Defaults to the branch resolved from --sha when possible.",
    )
    parser.add_argument(
        "--expect-production",
        action="store_true",
        help=(
            "Require the commit's production publish path to finish successfully: Self Deploy for push runs, "
            "or the CI/CD deploy job for manual workflow_dispatch runs."
        ),
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until workflows settle on success/failure/incomplete or until the timeout is hit.",
    )
    parser.add_argument("--poll-seconds", type=int, default=15, help="Polling interval when --wait is enabled.")
    parser.add_argument("--timeout-seconds", type=int, default=1800, help="Maximum wait time when --wait is enabled.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cwd = os.getcwd()
    auth_headers = resolve_auth_headers(cwd)
    repo = resolve_repo(cwd, args.repo)
    sha = resolve_sha(cwd, args.sha)
    branch = args.branch or resolve_branch(cwd, args.sha)

    deadline = time.time() + args.timeout_seconds
    last_payload: tuple[WorkflowSummary | None, WorkflowSummary | None, str, str] | None = None

    while True:
        runs = fetch_workflow_runs(repo, sha, auth_headers)
        ci_cd = summarize_run(
            repo,
            latest_run(runs, "CI/CD", branch=branch, allowed_events={"push", "workflow_dispatch"}),
            auth_headers,
        )
        self_deploy = summarize_run(
            repo,
            latest_run(
                runs,
                "Self Deploy",
                branch=branch,
                allowed_events={"workflow_run", "workflow_dispatch"},
            ),
            auth_headers,
        )
        state, message = overall_state(ci_cd, self_deploy, expect_production=args.expect_production)
        last_payload = (ci_cd, self_deploy, state, message)

        if not args.wait or state != "pending" or time.time() >= deadline:
            break
        time.sleep(args.poll_seconds)

    assert last_payload is not None
    ci_cd, self_deploy, state, message = last_payload
    if args.wait and state == "pending":
        message = f"{message} Timed out after {args.timeout_seconds} seconds."
    print_summary(repo, sha, ci_cd, self_deploy, state, message, json_output=args.json)
    return state_exit_code(state)


if __name__ == "__main__":
    sys.exit(main())
