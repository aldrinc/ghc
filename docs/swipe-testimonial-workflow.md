# Swipe Testimonial Workflow

This workflow stays external to the existing services and uses extracted testimonial images as the swipe inputs for the existing swipe image generation flow.

It gives you an external trigger path that:

- extracts a testimonial/template zip into a repo folder
- serves those template images locally
- sends each template image into the existing swipe generation workflow
- persists generated assets into MOS
- writes the resulting `assetPublicId` values back into the page draft

The CLI lives at:

- `scripts/swipe_testimonial_workflow.py`

## What It Reuses

It reuses:

- `POST /swipes/generate-image-ad`
- `GET /workflows/{workflow_run_id}`
- `GET /assets`
- `GET /funnels/{funnel_id}/pages/{page_id}`
- `PUT /funnels/{funnel_id}/pages/{page_id}`

## Commands

Extract a zip into a template image directory:

```bash
python3 scripts/swipe_testimonial_workflow.py prepare-templates \
  --zip /absolute/path/to/source-testimonials.zip \
  --output-dir /absolute/path/to/repo/template-images
```

`prepare-templates` strips a single enclosing folder from the zip when present, so the actual image files end up directly inside `template-images/`.

Inspect a live page and list image-like JSON pointers:

```bash
python3 scripts/swipe_testimonial_workflow.py inspect-page \
  --base-url "$MOS_BASE_URL" \
  --auth-token-env MOS_API_TOKEN \
  --funnel-id "<funnel-id>" \
  --page-id "<page-id>" \
  --page-source latestDraftOrApproved
```

Inspect a local Puck JSON file and list image-like JSON pointers:

```bash
python3 scripts/swipe_testimonial_workflow.py inspect-puck \
  --input mos/frontend/src/funnels/templates/salesPdp/defaults.json
```

Run the workflow from a config JSON:

```bash
python3 scripts/swipe_testimonial_workflow.py run \
  --config /absolute/path/to/workflow.json \
  --output /absolute/path/to/workflow-result.json
```

## Config Shape

Top-level fields:

- `mosBaseUrl`: required. Base URL for the MOS backend.
- `authTokenEnv`: required. Environment variable that holds the Bearer token used for MOS API requests.
- `templateImagesDir`: required. Absolute path to the extracted template image directory.
- `generationDefaults`: required. Default swipe generation inputs used unless a placement overrides them.
- `pages`: required. Array of page patch jobs.
- `patchedOutputDir`: required only when any page uses `saveDraft=false`.
- `sourceServeHost`: optional. Host used for the temporary file server that exposes the template files. Default `127.0.0.1`.
- `sourceServePort`: optional. Port for the temporary file server. Default `0` (ephemeral).

`generationDefaults` fields:

- `orgId`
- `clientId`
- `productId`
- `campaignId`
- `assetBriefId`
- `requirementIndex`
- `aspectRatio`
- `count`

Optional generation fields:

- `model`: omit to let the swipe service use `SWIPE_PROMPT_MODEL` or its normal backend env resolution
- `renderModelId`: omit to let the swipe service use `SWIPE_IMAGE_RENDER_MODEL`

`count` must be exactly `1`. This wrapper is slot-oriented and will error if you try to request multi-output generations.

Each `pages[]` entry must include:

- `funnelId`
- `pageId`
- `pageSource`: one of `latestDraft`, `latestApproved`, `latestDraftOrApproved`
- `saveDraft`: boolean
- `placements`: non-empty array

Each `placements[]` entry must include:

- `name`: label used in the run summary
- `templateFile`: template image file name from `templateImagesDir`, or an exact relative path inside that directory
- `slotPointer`: JSON pointer to the target image object in `puckData`
- `writePublicIdFields`: array of object fields to set with the generated `publicId`
- `clearFields`: array of object fields to delete after patching

Optional placement fields:

- `alt`
- `generation`: object with any overrides for `generationDefaults`

## Minimal Config Skeleton

```json
{
  "mosBaseUrl": "",
  "authTokenEnv": "",
  "templateImagesDir": "",
  "generationDefaults": {
    "orgId": "",
    "clientId": "",
    "productId": "",
    "campaignId": "",
    "assetBriefId": "",
    "requirementIndex": 0,
    "aspectRatio": "1:1",
    "count": 1
  },
  "pages": [
    {
      "funnelId": "",
      "pageId": "",
      "pageSource": "latestDraftOrApproved",
      "saveDraft": true,
      "placements": [
        {
          "name": "",
          "templateFile": "",
          "slotPointer": "",
          "writePublicIdFields": ["assetPublicId"],
          "clearFields": ["src"]
        }
      ]
    }
  ]
}
```

## Slot Mapping Notes

The script patches whatever object `slotPointer` resolves to. It does not infer page semantics.

Examples:

- Standard image slot: `writePublicIdFields=["assetPublicId"]`, `clearFields=["src"]`
- Sales PDP gallery slide: `writePublicIdFields=["assetPublicId","thumbAssetPublicId"]`, `clearFields=["src","thumbSrc"]`

If `slotPointer` resolves to the wrong object, the script will still patch that object. Use `inspect-page` or `inspect-puck` first.

## Template Image Notes

The workflow expects template images to already exist in `templateImagesDir`. You can create that directory with `prepare-templates`.

Use one canonical folder that contains the image files directly, for example:

- `/Users/auggieclement/Documents/GitHub/ghc/template-images`

The run command serves those template images over a temporary local HTTP server so the MOS backend can fetch them as `swipeImageUrl` inputs.

This means:

- local MOS backend: works directly with the default local file server
- remote MOS backend: the default local file server is not reachable; the script will error instead of silently pretending it worked

If you need a remote MOS backend, use a host value for `sourceServeHost` that is reachable from that backend.

## Env Loading

Use the backend start scripts when you want the service processes to resolve models from env:

- [scripts/start-backend.sh](/Users/auggieclement/Documents/GitHub/ghc/scripts/start-backend.sh)
- [scripts/start-worker.sh](/Users/auggieclement/Documents/GitHub/ghc/scripts/start-worker.sh)

They now launch through [run_with_backend_env.py](/Users/auggieclement/Documents/GitHub/ghc/scripts/run_with_backend_env.py), which loads:

- repo `.env`
- repo `.env.local.consolidated`
- `mos/backend/.env`

with the same `override=False` behavior the backend uses internally, so explicit process env still wins.

## Output

The run summary includes, per placement:

- resolved template member
- `workflowRunId`
- `temporalWorkflowId`
- render `jobId`
- generated `assetId`
- generated `publicId`

If `saveDraft=true`, the summary also includes the saved draft version id.

If `saveDraft=false`, the script writes patched `puckData` JSON files into `patchedOutputDir`.
