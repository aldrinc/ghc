# Testimonial Image Generation CLI

This documents [`testimonial_cli.py`](./testimonial_cli.py), the CLI wrapper for generating testimonial images through MOS backend endpoints.

The CLI does not render images locally. It:

- opens Chrome through Playwright
- gets a Clerk token from the MOS UI
- calls backend testimonial-generation endpoints
- downloads the generated assets into a local output directory

## Location

Run it from the repo root:

```bash
python scripts/testimonial_cli.py --help
```

Available commands:

- `pdp-examples generate`
- `swipe-template-testimonials generate`

## Requirements

- Python environment with the repo's backend dependencies installed
- Playwright available in that Python environment
- Google Chrome installed locally
- a reachable MOS backend URL
- a reachable MOS frontend URL for Clerk login
- access to the correct organization in the MOS UI

The CLI uses a persistent Chrome profile by default:

```text
~/.testimonial-cli/chrome-profile
```

That means the first run usually needs an interactive login, but later runs can reuse the same browser session until it expires.

## Common arguments

Both commands require:

- `--api-base-url`: MOS backend base URL, for example `http://localhost:8000`
- `--ui-url`: MOS frontend URL, for example `http://localhost:5173`

Optional shared auth arguments:

- `--jwt-template`: Clerk JWT template name. Default: `backend`
- `--profile-dir`: Chrome profile directory. Default: `~/.testimonial-cli/chrome-profile`

Example:

```bash
python scripts/testimonial_cli.py pdp-examples generate \
  --api-base-url http://localhost:8000 \
  --ui-url http://localhost:5173 \
  --funnel-id <funnel-id>
```

## Login flow

On startup, the CLI opens Chrome through Playwright and loads the MOS UI. If you are not already logged in, complete the login flow in that browser window.

The token must include an organization id. If the CLI says the token is missing `org_id`, switch to the correct organization in the MOS UI and rerun the command.

## Output directories

If you do not pass `--output-dir`, the CLI creates a timestamped directory under the current working directory:

```text
./outputs/<timestamp>-<command>
```

If you do pass `--output-dir`, that directory must not already exist. The CLI creates it and fails instead of overwriting an existing directory.

## Command: `pdp-examples generate`

Use this when you want the 5 Sales PDP testimonial example images for a funnel page.

What it does:

1. Resolves the target Sales PDP page.
2. Builds the backend request payload.
3. Calls `POST /funnels/{funnel_id}/pages/{page_id}/ai/sales-pdp-examples`.
4. Downloads the 5 generated images from public asset URLs.
5. Writes request/response/manifest files into the output directory.

### Required arguments

- `--funnel-id`

### Optional arguments

- `--page-id`: use a specific page instead of auto-resolving the sales page
- `--page-source`: `latest-draft` or `latest-approved`
  Default: `latest-draft`
- `--draft-version-id`: send an explicit draft version id to the backend
- `--current-puck-data`: path to a local JSON file to send as `currentPuckData`
- `--model`: override the backend generation model
- `--temperature`: default `0.3`
- `--max-tokens`
- `--max-duration-seconds`
- `--output-dir`

### Page resolution behavior

If `--page-id` is omitted, the CLI fetches the funnel and expects exactly one eligible Sales PDP page:

- page slug `sales`, or
- page template id `sales-pdp`

If there are zero or multiple matches, the CLI fails and tells you to pass `--page-id`.

If neither `--draft-version-id` nor `--current-puck-data` is provided, the CLI fetches page data from the backend using `--page-source`.

### Example

```bash
python scripts/testimonial_cli.py pdp-examples generate \
  --api-base-url http://localhost:8000 \
  --ui-url http://localhost:5173 \
  --funnel-id 11111111-2222-3333-4444-555555555555 \
  --page-source latest-draft \
  --temperature 0.3
```

### Files written

The command writes:

- 5 downloaded image files
- `request.json`
- `backend-response.json`
- `manifest.json`

The backend is expected to return exactly these variants:

- `standard_ugc`
- `qa_ugc`
- `bold_claim`
- `personal_highlight`
- `dorm_selfie`

If any variant is missing or duplicated, the CLI fails.

## Command: `swipe-template-testimonials generate`

Use this when you want to generate swipe-style testimonial outputs for a campaign asset brief using local template images.

What it does:

1. Loads the campaign and asset brief from MOS.
2. Resolves the funnel and a staging sales page.
3. Scans the repo-level `template-images/` directory.
4. Uploads each local template image as a page attachment.
5. Starts one swipe image workflow for each image requirement and each staged template image.
6. Waits for all workflows to complete.
7. Downloads the generated public assets and writes a manifest.

### Required arguments

- `--campaign-id`
- `--asset-brief-id`

### Optional arguments

- `--aspect-ratio`: default `4:5` for feed-sized outputs
- `--model`
- `--render-model-id`
- `--max-output-tokens`
- `--poll-interval-seconds`: default `5`
- `--output-dir`

### Template image source

This command reads from the repo-level `template-images/` directory.

Rules:

- the directory must exist
- it must contain at least one file
- hidden files are ignored
- allowed file types are `png`, `jpeg`, `jpg`, `webp`, and `gif`

Every valid file under that directory is staged and used.

### Staging page resolution behavior

The CLI resolves a staging page from the funnel attached to the asset brief:

- if the funnel has exactly one page, it uses that page
- otherwise it expects exactly one page with slug `sales` or template id `sales-pdp`

If it cannot resolve a single page, it fails with a descriptive error.

### Example

```bash
python scripts/testimonial_cli.py swipe-template-testimonials generate \
  --api-base-url http://localhost:8000 \
  --ui-url http://localhost:5173 \
  --campaign-id 11111111-2222-3333-4444-555555555555 \
  --asset-brief-id brief-123 \
  --aspect-ratio 4:5
```

### Files written

The command writes:

- one downloaded output image per completed workflow
- `request.json`
- `manifest.json`

The manifest includes:

- campaign, client, product, and funnel ids
- staging page id
- image requirement indexes
- workflow ids
- staged asset ids and URLs
- generated asset ids and public ids
- local file paths for downloaded results

## Exit behavior

The CLI exits with:

- `0` on success
- `1` on any runtime validation or backend error

It is intentionally strict. It fails when required data is missing instead of guessing.

## Troubleshooting

- `Timed out ... waiting for a valid Clerk session token`
  Complete login in the opened Chrome window and make sure the correct org is selected.
- `Clerk session token is missing org_id`
  Switch organizations in the MOS UI before rerunning.
- `Could not resolve a Sales PDP page`
  Pass `--page-id` explicitly for `pdp-examples generate`.
- `Template image directory does not exist` or `is empty`
  Create/populate `template-images/` before running the swipe command.
- `unsupported content type`
  Convert the template file to `png`, `jpg`, `jpeg`, `webp`, or `gif`.
- `output dir ... already exists`
  Use a new `--output-dir` path or let the CLI create a timestamped one.

## Related files

- [`testimonial_cli.py`](./testimonial_cli.py)
- [`browser_session_auth.py`](./lib/browser_session_auth.py)
- [`mos_api_client.py`](./lib/mos_api_client.py)
- [`testimonial-renderer/README.md`](../testimonial-renderer/README.md)
