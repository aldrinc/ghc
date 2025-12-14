# Taskmaster AI — Project Management Guide

Use Taskmaster AI to turn PRDs into executable task plans and keep status in sync.

## Install & Initialize
- Install globally: `npm install -g task-master-ai`
- In the project root (already done here): `task-master init -y`
- Artifacts live in `.taskmaster/` (config, tasks, reports, templates). Default state is in `.taskmaster/state.json`.

## Configure Models & Keys
- Add provider keys (e.g., `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) to `.env` using `.env.example` as a template.
- Pick models: `task-master models --setup` (or `task-master models --set-main <model_id>` etc.).

## Turn a PRD into Tasks
- Place your PRD at `prd.txt` (or point to another file).
- Generate tasks: `task-master parse-prd --input prd.txt --num-tasks 12`
- List what was created: `task-master list --with-subtasks`
- If needed, auto-generate task files: `task-master generate`

## Break Down & Refine
- Analyze complexity: `task-master analyze-complexity --research`
- Expand all pending tasks: `task-master expand --all --research`
- Update with new info: `task-master update --from=<id> --prompt="key changes"` or single task via `update-task <id> <prompt>`.

## Manage Execution
- Find the next task respecting dependencies: `task-master next`
- Set status: `task-master set-status <id> in-progress|review|done|deferred|cancelled`
- Add work items: `task-master add-task --prompt="short goal"`; add subtasks: `task-master add-subtask --parent=<id> --title="..."`.
- Manage dependencies: `task-master add-dependency --id=<id> --depends-on=<id>`
- Use tags to separate streams: `task-master add-tag feature-x` then `task-master use-tag feature-x`.

## Share Progress
- Export to README: `task-master sync-readme --with-subtasks`
- View reports: check `.taskmaster/reports/` after running analysis commands.

## Handy References
- CLI help: `task-master --help`
- Templates to start a PRD: `.taskmaster/templates/example_prd.txt` and `example_prd_rpg.txt`
- Task files: `.taskmaster/tasks/`; docs: `.taskmaster/docs/`
