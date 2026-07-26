import logging
from typing import Any, Iterator

import requests

logger = logging.getLogger(__name__)


class PhotoPrismError(RuntimeError):
    pass


class PhotoPrismClient:
    """Minimal client for the PhotoPrism REST API.

    PhotoPrism does not publish a stable, versioned API contract, so this
    client intentionally keeps its assumptions small and verifiable:
    it authenticates, lists/fetches photos, downloads a preview image and
    updates a photo by round-tripping the full record (GET, patch in
    memory, PUT) - the same pattern the PhotoPrism web UI itself uses.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self.timeout = timeout
        self._session = requests.Session()

    # -- auth -----------------------------------------------------------

    def authenticate(self) -> None:
        if self._client_id and self._client_secret:
            self._authenticate_oauth()
        elif self._username and self._password:
            self._authenticate_session()
        else:
            raise PhotoPrismError(
                "No PhotoPrism credentials configured: set either "
                "PHOTOPRISM_CLIENT_ID/PHOTOPRISM_CLIENT_SECRET (recommended, "
                "create an OAuth client under Settings > Applications) or "
                "PHOTOPRISM_USERNAME/PHOTOPRISM_PASSWORD."
            )

    def _authenticate_oauth(self) -> None:
        resp = self._session.post(
            f"{self.base_url}/api/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            timeout=self.timeout,
        )
        if not resp.ok:
            raise PhotoPrismError(
                f"PhotoPrism OAuth login failed ({resp.status_code}): {resp.text[:300]}"
            )
        token = resp.json().get("access_token")
        if not token:
            raise PhotoPrismError("PhotoPrism OAuth response did not contain an access_token")
        self._session.headers["Authorization"] = f"Bearer {token}"

    def _authenticate_session(self) -> None:
        resp = self._session.post(
            f"{self.base_url}/api/v1/session",
            json={"username": self._username, "password": self._password},
            timeout=self.timeout,
        )
        if not resp.ok:
            raise PhotoPrismError(
                f"PhotoPrism session login failed ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        token = data.get("access_token") or resp.headers.get("X-Session-ID") or data.get("id")
        if not token:
            raise PhotoPrismError("PhotoPrism session response did not contain a token/id")
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._session.headers["X-Session-ID"] = token

    # -- photos -----------------------------------------------------------

    def iter_photos(self, batch_size: int = 100, max_photos: int = 0) -> Iterator[dict[str, Any]]:
        offset = 0
        fetched = 0
        while True:
            params = {
                "count": batch_size,
                "offset": offset,
                "order": "added",
                "merged": "true",
            }
            resp = self._session.get(
                f"{self.base_url}/api/v1/photos", params=params, timeout=self.timeout
            )
            if not resp.ok:
                raise PhotoPrismError(
                    f"Listing photos failed ({resp.status_code}): {resp.text[:300]}"
                )
            page = resp.json()
            if not page:
                return
            for photo in page:
                yield photo
                fetched += 1
                if max_photos and fetched >= max_photos:
                    return
            if len(page) < batch_size:
                return
            offset += batch_size

    def get_random_photo(self) -> dict[str, Any] | None:
        """Fetch a single random photo, used by the `--random` test mode."""
        resp = self._session.get(
            f"{self.base_url}/api/v1/photos",
            params={"count": 1, "order": "random"},
            timeout=self.timeout,
        )
        if not resp.ok:
            raise PhotoPrismError(
                f"Fetching a random photo failed ({resp.status_code}): {resp.text[:300]}"
            )
        page = resp.json()
        return page[0] if page else None

    def get_photo(self, uid: str) -> dict[str, Any]:
        resp = self._session.get(f"{self.base_url}/api/v1/photos/{uid}", timeout=self.timeout)
        if not resp.ok:
            raise PhotoPrismError(
                f"Fetching photo {uid} failed ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    def update_photo(self, uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge `patch` into the current record and PUT the whole thing back.

        PhotoPrism does not document a minimal partial-update payload, so the
        robust approach is to fetch the full record, apply the change
        everywhere the field plausibly lives (top-level and/or `Details`),
        and write the whole object back - unknown/duplicate keys are ignored
        by the server, so this is safe across PhotoPrism versions.
        """
        current = self.get_photo(uid)
        merged = _deep_merge(current, patch)
        resp = self._session.put(
            f"{self.base_url}/api/v1/photos/{uid}", json=merged, timeout=self.timeout
        )
        if not resp.ok:
            raise PhotoPrismError(
                f"Updating photo {uid} failed ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    def download_preview(self, uid: str) -> bytes:
        resp = self._session.get(f"{self.base_url}/api/v1/photos/{uid}/dl", timeout=self.timeout)
        if not resp.ok:
            raise PhotoPrismError(
                f"Downloading preview for {uid} failed ({resp.status_code}). "
                "Make sure the OAuth client / app password has the 'download' scope."
            )
        return resp.content


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
