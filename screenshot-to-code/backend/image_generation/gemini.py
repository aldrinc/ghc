# pyright: reportAttributeAccessIssue=false, reportMissingImports=false
import base64

from google import genai
from google.genai import types


GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"


def _extract_generated_image_data_url(
    response: types.GenerateContentResponse,
) -> str:
    for candidate in response.candidates or []:
        content = candidate.content
        if content is None:
            continue

        for part in content.parts or []:
            inline_data = part.inline_data
            if (
                inline_data is None
                or inline_data.mime_type is None
                or not inline_data.mime_type.startswith("image/")
            ):
                continue

            encoded = base64.b64encode(inline_data.data).decode("ascii")
            return f"data:{inline_data.mime_type};base64,{encoded}"

    raise ValueError("Gemini image generation returned no image data.")


async def generate_image_gemini(prompt: str, api_key: str) -> str:
    client = genai.Client(api_key=api_key)
    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.TEXT, types.Modality.IMAGE]
            ),
        )
    finally:
        await client.aio.aclose()

    return _extract_generated_image_data_url(response)
