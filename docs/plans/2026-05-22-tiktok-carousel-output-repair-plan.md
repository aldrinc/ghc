# TikTok Carousel Output Repair Plan

Status: implemented  
Owner: Codex / Aldrin  
Date: 2026-05-22

## Goal

Repair the Social Agents page so the six-slide TikTok variant output matches the Larry skill structure instead of a dummy smoke-test storyboard.

## Scope

- Load the Larry skill package as source truth.
- Add the Larry six-slide formula to the Social Agents page.
- Preserve manual line breaks inside each slide using `---` slide separators.
- Add base image prompt capture.
- Add a 9:16 draft output preview for all six slides.
- Add a source-image generation action that uses the existing MOS image generator and the current configured image model.
- Add a rendered output path: six source images in, six 9:16 PNG assets out with Larry-style text overlays burned into the image.
- Keep Postiz as handoff owner; do not publish.

## Acceptance

- Draft preview shows exactly six 9:16 slides.
- Slide purposes match Larry: hook, problem, discovery, transformation, escalation, CTA.
- Manual overlay line breaks stay inside each slide instead of becoming extra slides.
- Operator can generate six source images from the Larry slide prompts without changing model configuration.
- Rendered output requires exactly six source images and produces six downloadable PNG assets.
- Chrome local preview shows the repaired output with no console errors.
- Frontend test and build pass.

## Verification

- `cd mos/frontend && npm run test:unit -- src/pages/workspaces/SocialAgentsPage.test.tsx`
- `cd mos/frontend && npm run build`
- Chrome local preview screenshot exists.
- Rendered output screenshot and six PNG assets exist.
- Larry source manifest verifies.
