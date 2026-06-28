from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

import httpx

MODEL = "models/gemini-3.1-flash-image-preview"
DEFAULT_PROMPT = (
    "Edit the attached image. Remove only the visible product object or product packaging. "
    "Do not change people, text, typography, layout, background, colors, lighting, crop, or any other object. "
    "Do not add a replacement object. Leave the removed area as the natural continuation of the existing image."
)


def extract_inline_image(payload: dict[str, Any]) -> tuple[bytes, str]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini response missing candidates[]")
    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            inline = part.get("inlineData") if isinstance(part, dict) else None
            if not isinstance(inline, dict):
                continue
            mime_type = inline.get("mimeType")
            data = inline.get("data")
            if not isinstance(mime_type, str) or not isinstance(data, str):
                raise RuntimeError("Gemini inline image was missing mimeType or data")
            return base64.b64decode(data, validate=True), mime_type
    raise RuntimeError("Gemini response did not include an inline image")


def edit_image(input_path: Path, output_path: Path) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")
    image_bytes = input_path.read_bytes()
    mime_type = mimetypes.guess_type(str(input_path))[0] or "image/jpeg"
    prompt = os.environ.get("PRODUCT_REMOVE_PROMPT", "").strip() or DEFAULT_PROMPT
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(image_bytes).decode("utf-8"),
                        }
                    },
                ],
            }
        ]
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/{MODEL}:generateContent"
    with httpx.Client(timeout=180.0) as client:
        response = client.post(url, params={"key": api_key}, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini image edit failed ({response.status_code}): {response.text[:2000]}")
    edited_bytes, edited_mime_type = extract_inline_image(response.json())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(edited_bytes)
    return {
        "inputPath": str(input_path),
        "outputPath": str(output_path),
        "prompt": prompt,
        "model": MODEL,
        "inputMimeType": mime_type,
        "outputMimeType": edited_mime_type,
        "outputSizeBytes": len(edited_bytes),
    }


def main() -> None:
    if len(sys.argv) < 3 or len(sys.argv[1:]) % 2 != 0:
        raise SystemExit("Usage: edit_remove_product_only.py input1 output1 [input2 output2 ...]")
    results = []
    args = sys.argv[1:]
    for i in range(0, len(args), 2):
        results.append(edit_image(Path(args[i]), Path(args[i + 1])))
    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()
