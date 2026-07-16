"""Image generation strategies for different API formats.

Each strategy encapsulates how to build a request body and parse a response
for a specific image generation API format.
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from pathlib import Path


class ImageGenerationStrategy(ABC):
    """Abstract strategy for image generation API calls."""

    @property
    @abstractmethod
    def default_api_path(self) -> str:
        """Default API path when model config api_path is empty."""
        ...

    @abstractmethod
    def build_request(
        self,
        model_name: str,
        prompt: str,
        size: str | None = None,
        reference_images: list[str] | None = None,
    ) -> dict:
        """Build the JSON request body for an image generation call."""
        ...

    @abstractmethod
    def parse_response(self, response_data: dict) -> dict:
        """Parse the response body, returning at least {'url': str, 'raw': dict}."""
        ...

    @staticmethod
    def resolve_image_ref(url: str) -> str:
        """Resolve a local storage path to a base64 data URI, pass through URLs unchanged."""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("/api/files/media/"):
            from backend.app.core.config import get_settings

            file_name = url.split("/")[-1]
            local = Path(get_settings().storage_dir) / "media" / file_name
            if local.is_file():
                raw = local.read_bytes()
                ext = local.suffix.lower().lstrip(".")
                mime = {
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "png": "image/png",
                    "gif": "image/gif",
                    "webp": "image/webp",
                }.get(ext, "image/png")
                return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        return url


class OpenAICompatibleStrategy(ImageGenerationStrategy):
    """OpenAI-compatible /v1/images/generations endpoint."""

    @property
    def default_api_path(self) -> str:
        return "/v1/images/generations"

    def build_request(
        self,
        model_name: str,
        prompt: str,
        size: str | None = None,
        reference_images: list[str] | None = None,
    ) -> dict:
        body: dict = {
            "model": model_name,
            "prompt": prompt,
            "n": 1,
            "response_format": "url",
        }
        if size:
            body["size"] = size
        if reference_images:
            resolved = [self.resolve_image_ref(url) for url in reference_images]
            if len(resolved) == 1:
                body["image"] = resolved[0]
            else:
                body["image"] = resolved
                body["sequential_image_generation"] = "disabled"
            body["watermark"] = False
        return body

    def parse_response(self, response_data: dict) -> dict:
        try:
            item = response_data["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Image response missing data[0]") from exc
        image_ref = item.get("url") or item.get("b64_json")
        if not isinstance(image_ref, str) or not image_ref:
            raise ValueError("Image response missing url or b64_json")
        return {"url": image_ref, "raw": response_data}


class GrsAIStrategy(ImageGenerationStrategy):
    """GrsAI中转站 /v1/api/generate endpoint (gpt-image-2 custom format)."""

    @property
    def default_api_path(self) -> str:
        return "/v1/api/generate"

    def build_request(
        self,
        model_name: str,
        prompt: str,
        size: str | None = None,
        reference_images: list[str] | None = None,
    ) -> dict:
        body: dict = {
            "model": model_name,
            "prompt": prompt,
            "replyType": "json",
        }
        if size:
            body["aspectRatio"] = size
        if reference_images:
            body["images"] = [self.resolve_image_ref(url) for url in reference_images]
        return body

    def parse_response(self, response_data: dict) -> dict:
        status = response_data.get("status")
        if status == "failed":
            raise ValueError(f"Image generation failed: {response_data.get('error', 'unknown')}")
        results = response_data.get("results", [])
        if not results:
            raise ValueError("Image response missing results")
        url = results[0].get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("Image response missing url in results[0]")
        return {"url": url, "raw": response_data}


STRATEGY_REGISTRY: dict[str, ImageGenerationStrategy] = {
    "openai": OpenAICompatibleStrategy(),
    "grsai": GrsAIStrategy(),
}


def get_strategy(api_format: str) -> ImageGenerationStrategy:
    """Get the image generation strategy for the given format, falling back to OpenAI."""
    return STRATEGY_REGISTRY.get(api_format, STRATEGY_REGISTRY["openai"])
