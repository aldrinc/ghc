# Template Image Trace Batch

Use [run_template_image_trace_batch.py](/Users/auggieclement/Documents/GitHub/ghc/scripts/run_template_image_trace_batch.py) when you want to run the repo’s consolidated `template-image-workspace/assets/` directory through the existing swipe image creation workflow while forcing stage two onto mOS’s embedded `creative_service` provider.

This script does not call the swipe activity directly. It starts the same `POST /swipes/generate-image-ad` workflow used by the swipe path, waits on the workflow result, then downloads and records the generated assets.

## Behavior

- Defaults `--template-dir` to `/Users/auggieclement/Documents/GitHub/ghc/template-image-workspace/assets`
- Defaults `--output-root` to `/Users/auggieclement/Documents/GitHub/ghc/template-image-workspace/output/trace-batch`
- Iterates the repo `template-image-workspace/assets/` directory as workflow inputs
- Starts the normal swipe image workflow for each file
- Errors if the resolved stage-two provider is not `creative_service`
- Passes through the existing stage-one `--model` and stage-two `--render-model-id` arguments
- Writes `index.json`, `index.html`, per-file success metadata, diagnostics, and downloaded outputs under `--output-root`

## Example

```bash
mos/backend/.venv/bin/python scripts/run_template_image_trace_batch.py \
  --mos-base-url "http://127.0.0.1:8008" \
  --auth-token-env MOS_API_TOKEN \
  --client-id "<client-id>" \
  --product-id "<product-id>" \
  --campaign-id "<campaign-id>" \
  --asset-brief-id "<asset-brief-id>" \
  --render-model-id "models/gemini-3.1-flash-image-preview"
```

If you want a different run folder, pass `--output-root` under `/Users/auggieclement/Documents/GitHub/ghc/template-image-workspace/output/...`.

If `--render-model-id` is omitted, the script uses the backend env resolution already in place and will fail unless that existing configuration still resolves to `creative_service`.

The provider check is intentionally limited to local backends. If `--mos-base-url` is not local, the script errors instead of pretending it can verify a remote backend’s render configuration.
