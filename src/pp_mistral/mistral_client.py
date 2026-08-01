import base64
import json
import logging
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a photo cataloguing assistant for a personal photo library. "
    "Analyse the given photo and respond with a single JSON object, no "
    "markdown, matching exactly this schema:\n"
    '{"description": string, "keywords": [string, ...], '
    '"location_guess": {"confidence": "none"|"low"|"medium"|"high", "place": string|null}}\n'
    "Rules:\n"
    "- description: one or two factual sentences describing what is visible.\n"
    "- keywords: 5 to 12 short, lowercase, singular English keywords "
    "(subjects, objects, setting, mood, season - no hashtags).\n"
    "- location_guess: only if the image itself contains visual evidence of "
    "a specific place (landmark, signage, license plates, architecture "
    "style, vegetation, etc). Set confidence to 'none' and place to null if "
    "you would just be guessing without real evidence. 'place' should be a "
    "short, geocodable string such as 'Eiffel Tower, Paris, France'."
)


class MistralError(RuntimeError):
    pass


@dataclass
class PhotoAnalysis:
    description: str | None = None
    keywords: list[str] = field(default_factory=list)
    location_confidence: str = "none"
    location_place: str | None = None


class MistralClient:
    def __init__(
        self,
        api_key: str,
        model: str = "mistral-small-latest",
        timeout: float = 60.0,
    ) -> None:
        self._model = model
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_key}"

    def analyze_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> PhotoAnalysis:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{b64}"
        payload = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyse this photo."},
                        {"type": "image_url", "image_url": data_url},
                    ],
                },
            ],
        }
        resp = self._session.post(MISTRAL_API_URL, json=payload, timeout=self.timeout)
        if not resp.ok:
            raise MistralError(f"Mistral API request failed ({resp.status_code}): {resp.text[:300]}")
        body = resp.json()
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise MistralError(f"Unexpected Mistral response shape: {body}") from exc
        return parse_analysis(content)


def parse_analysis(content: str) -> PhotoAnalysis:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise MistralError(f"Mistral did not return valid JSON: {content[:300]}") from exc

    location = data.get("location_guess") or {}
    keywords = [str(k).strip().lower() for k in data.get("keywords", []) if str(k).strip()]
    return PhotoAnalysis(
        description=(data.get("description") or "").strip() or None,
        keywords=keywords,
        location_confidence=str(location.get("confidence") or "none").lower(),
        location_place=(location.get("place") or None),
    )
