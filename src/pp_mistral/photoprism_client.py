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
        self._preview_token: str | None = None

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"
        try:
            return self._session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise PhotoPrismError(
                f"Could not reach PhotoPrism at {url}: {exc}. This is a network "
                "reachability issue, not an application error - check that "
                "PHOTOPRISM_URL is correct, and that this container can "
                "actually reach it (e.g. `docker compose exec photoprism-mistral "
                "curl -v $PHOTOPRISM_URL` should get a response). If the Docker "
                "host itself can reach PhotoPrism but the container can't, try "
                "`network_mode: host` in docker-compose.yml (Linux only), or "
                "check firewall/forwarding rules and any VPN routes on the host."
            ) from exc

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
        resp = self._request(
            "POST",
            "/api/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
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
        resp = self._request(
            "POST",
            "/api/v1/session",
            json={"username": self._username, "password": self._password},
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
            resp = self._request("GET", "/api/v1/photos", params=params)
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
        resp = self._request("GET", "/api/v1/photos", params={"count": 1, "order": "random"})
        if not resp.ok:
            raise PhotoPrismError(
                f"Fetching a random photo failed ({resp.status_code}): {resp.text[:300]}"
            )
        page = resp.json()
        return page[0] if page else None

    def get_photo(self, uid: str) -> dict[str, Any]:
        resp = self._request("GET", f"/api/v1/photos/{uid}")
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
        resp = self._request("PUT", f"/api/v1/photos/{uid}", json=merged)
        if not resp.ok:
            raise PhotoPrismError(
                f"Updating photo {uid} failed ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    def get_config(self) -> dict[str, Any]:
        resp = self._request("GET", "/api/v1/config")
        if not resp.ok:
            raise PhotoPrismError(f"Fetching config failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def _get_preview_token(self) -> str:
        if self._preview_token is None:
            config = self.get_config()
            token = (
                config.get("previewToken")
                or config.get("PreviewToken")
                or config.get("downloadToken")
                or config.get("DownloadToken")
            )
            if not token:
                raise PhotoPrismError(
                    "Could not find a previewToken/downloadToken in the PhotoPrism "
                    "config response - can't build thumbnail URLs."
                )
            self._preview_token = token
        return self._preview_token

    def download_thumbnail(self, photo: dict[str, Any], size: str = "fit_1920") -> bytes:
        """Download a server-generated thumbnail instead of the original file.

        `GET /api/v1/photos/:uid/dl` requires a separate download permission/
        token and returned 403 for plain session/OAuth auth in practice.
        Thumbnails use a different, more permissive mechanism
        (`GET /api/v1/t/:hash/:token/:size`) designed for previews, which is
        also all we need since we downscale the image ourselves anyway.
        """
        file_hash = _primary_file_hash(photo)
        if not file_hash:
            raise PhotoPrismError(f"Photo {photo.get('UID')} has no file hash to build a thumbnail URL from")
        token = self._get_preview_token()
        resp = self._request("GET", f"/api/v1/t/{file_hash}/{token}/{size}")
        if not resp.ok:
            raise PhotoPrismError(
                f"Downloading thumbnail for {photo.get('UID')} failed ({resp.status_code}): "
                f"{resp.text[:200]}"
            )
        return resp.content

    def download_preview(self, uid: str) -> bytes:
        """Fallback: download the original file via the `/dl` endpoint.

        Requires the download permission/scope on the account or OAuth
        client - prefer `download_thumbnail()` where possible.
        """
        resp = self._request("GET", f"/api/v1/photos/{uid}/dl")
        if not resp.ok:
            raise PhotoPrismError(
                f"Downloading preview for {uid} failed ({resp.status_code}). "
                "Make sure the OAuth client / app password has the 'download' scope."
            )
        return resp.content


def _primary_file_hash(photo: dict[str, Any]) -> str | None:
    # Search/list results (GET /api/v1/photos) carry the primary file's hash
    # directly at the top level - that's what the PhotoPrism web UI itself
    # uses to build thumbnail URLs for gallery grids. GET /api/v1/photos/:uid
    # (single record) instead nests it under Files.
    if photo.get("Hash"):
        return photo["Hash"]
    files = photo.get("Files") or []
    if not files:
        return None
    for f in files:
        if f.get("Primary"):
            return f.get("Hash")
    return files[0].get("Hash")


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
