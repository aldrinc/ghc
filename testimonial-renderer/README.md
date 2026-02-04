# Testimonial Renderer

Generates testimonial images from JSON input using HTML/CSS templates and Playwright. Includes an optional Nano Banana (Gemini) image generation flow for avatars and attachments.

## Requirements

- Node.js 18+
- Playwright browser install
- `GEMINI_API_KEY` set in your environment for Nano Banana flows

## Install

```bash
npm install
npx playwright install chromium
```

## Input schema

```json
{
  "template": "review_card",
  "name": "Vicki Cospar",
  "verified": true,
  "rating": 5,
  "review": "The puppy pads work awesome ...",
  "heroImageUrl": "./samples/assets/hero-puppies.svg",
  "meta": {
    "location": "Savannah, GA",
    "date": "2026-01-15"
  }
}
```

```json
{
  "template": "social_comment",
  "header": {
    "title": "All comments",
    "showSortIcon": true
  },
  "comments": [
    {
      "name": "Alex Johnson",
      "text": "I have so many questions",
      "avatarUrl": "./samples/assets/avatar-elaine.svg",
      "meta": {
        "time": "3d",
        "followLabel": "Follow"
      },
      "reactionCount": 34,
      "viewRepliesText": "View 1 reply",
      "replies": [
        {
          "name": "Lee Smith",
          "text": "@Alex Johnson would have been fun to watch and see how they did that",
          "avatarUrl": "./samples/assets/avatar-tina.svg",
          "meta": {
            "time": "3d"
          },
          "reactionCount": 8
        }
      ]
    }
  ]
}
```

### Template requirements

- `review_card`
  - Required: `name`, `verified`, `rating`, `review`
  - Optional: `heroImageUrl`, `avatarUrl`, `meta`
- `social_comment`
  - Required: `header`, `comments`
  - `header` requires: `title`, `showSortIcon`
  - Each comment requires: `name`, `text`, `avatarUrl`, `meta`
  - `meta` requires: `time`; optional: `followLabel`, `authorLabel`
  - Optional per comment: `reactionCount`, `attachmentUrl`, `viewRepliesText`, `replies[]`

### Validation rules

- `rating` must be an integer 1–5.
- `review` max length: 800 characters.
- `comment.text` max length: 600 characters.
- `name` max length: 80 characters.
- `header.title` max length: 40 characters.
- `meta.time` max length: 24 characters.
- `reactionCount` must be a non-negative integer when provided.
- `followLabel`/`authorLabel` max length: 24 characters.
- Image paths must resolve to an existing file (or a valid HTTP/HTTPS URL).

## Render a single image

```bash
npm run render -- --input samples/inputs/review_card.json --output samples/output/review_card.png
```

## Render a batch

```bash
npm run render -- --batch samples/inputs/batch.json --outdir samples/output
```

Each batch item must include an `output` filename.

## Run the service

```bash
npm run server
```

POST JSON to `http://localhost:4545/render?format=png` or `format=webp` (format is required).

## Nano Banana flow (generate assets + render)

This flow generates avatar and content images first, then injects them into one or more render payloads.

```bash
npm run render:nano -- --input samples/inputs/nano_banana_flow.json
```

See `samples/inputs/nano_banana_flow.json` for the full schema.

## Templates

- `src/templates/review_card.html`
- `src/templates/social_comment.html`

## Samples

- Input JSON: `samples/inputs/`
- Assets: `samples/assets/`
- Generated assets: `samples/generated/`
- Output images: `samples/output/`
