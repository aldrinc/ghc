# pyright: reportMissingImports=false
import pytest
from google.genai import types

from image_generation.gemini import _extract_generated_image_data_url


def test_extract_generated_image_data_url_returns_first_inline_image() -> None:
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="Generated image"),
                        types.Part(
                            inline_data=types.Blob(
                                data=b"fake-image-bytes",
                                mime_type="image/png",
                            )
                        ),
                    ],
                )
            )
        ]
    )

    assert (
        _extract_generated_image_data_url(response)
        == "data:image/png;base64,ZmFrZS1pbWFnZS1ieXRlcw=="
    )


def test_extract_generated_image_data_url_raises_without_image() -> None:
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="No image returned")],
                )
            )
        ]
    )

    with pytest.raises(ValueError, match="returned no image data"):
        _extract_generated_image_data_url(response)
