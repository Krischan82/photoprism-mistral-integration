import logging
import time
from typing import Any

from .config import Settings
from .geocode import geocode_place
from .image_utils import resize_image
from .mistral_client import MistralClient, MistralError, PhotoAnalysis
from .photoprism_client import PhotoPrismClient, PhotoPrismError

logger = logging.getLogger(__name__)

GEO_REVIEW_KEYWORD = "ai:location-guess"
MIN_LOCATION_CONFIDENCE = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _current_description(photo: dict[str, Any]) -> str | None:
    if photo.get("Description"):
        return photo["Description"]
    details = photo.get("Details") or {}
    return details.get("Description") or None


def _current_keywords(photo: dict[str, Any]) -> list[str]:
    details = photo.get("Details") or {}
    raw = details.get("Keywords") or ""
    return [k.strip() for k in raw.replace(",", " ").split() if k.strip()]


def _has_location(photo: dict[str, Any]) -> bool:
    return bool(photo.get("Lat")) and bool(photo.get("Lng"))


def _download_image(pp: PhotoPrismClient, photo: dict[str, Any]) -> bytes:
    """Download an image to analyse, preferring the thumbnail endpoint.

    `photos/:uid/dl` (the original file) needs the account/OAuth client to
    have download permission, which not every setup grants - the thumbnail
    endpoint is more permissive and is all we need since we downscale the
    image ourselves anyway. Falls back to the original if thumbnails fail.
    """
    uid = photo.get("UID")
    try:
        return pp.download_thumbnail(photo)
    except PhotoPrismError as exc:
        logger.warning("Thumbnail download failed for %s (%s), falling back to /dl", uid, exc)
        return pp.download_preview(uid)


def needs_processing(photo: dict[str, Any], settings: Settings) -> bool:
    if settings.overwrite_existing:
        return True
    if settings.enable_description and not _current_description(photo):
        return True
    if settings.enable_keywords and not _current_keywords(photo):
        return True
    if settings.enable_geolocation and not _has_location(photo):
        return True
    return False


def build_patch(photo: dict[str, Any], analysis: PhotoAnalysis, settings: Settings) -> dict[str, Any]:
    patch: dict[str, Any] = {}

    if settings.enable_description and analysis.description:
        if settings.overwrite_existing or not _current_description(photo):
            patch["Description"] = analysis.description
            patch.setdefault("Details", {})["Description"] = analysis.description

    if settings.enable_keywords and analysis.keywords:
        existing = _current_keywords(photo)
        if settings.overwrite_existing:
            merged = analysis.keywords
        else:
            merged = existing + [k for k in analysis.keywords if k not in existing]
        if merged != existing:
            patch.setdefault("Details", {})["Keywords"] = ", ".join(merged)

    if (
        settings.enable_geolocation
        and not _has_location(photo)
        and MIN_LOCATION_CONFIDENCE.get(analysis.location_confidence, 0)
        >= MIN_LOCATION_CONFIDENCE["medium"]
        and analysis.location_place
    ):
        coords = geocode_place(analysis.location_place, settings.geocode_user_agent)
        if coords:
            lat, lng = coords
            patch["Lat"] = lat
            patch["Lng"] = lng

            details_patch = patch.setdefault("Details", {})
            current_keywords = details_patch.get("Keywords")
            keyword_list = (
                [k.strip() for k in current_keywords.split(",") if k.strip()]
                if current_keywords
                else _current_keywords(photo)
            )
            if GEO_REVIEW_KEYWORD not in keyword_list:
                keyword_list.append(GEO_REVIEW_KEYWORD)
            details_patch["Keywords"] = ", ".join(keyword_list)

            logger.info(
                "Guessed location %r -> %s,%s", analysis.location_place, lat, lng
            )
        else:
            logger.info("Could not geocode guessed place %r", analysis.location_place)

    return patch


def run_once(settings: Settings) -> int:
    pp = PhotoPrismClient(
        settings.photoprism_url,
        client_id=settings.photoprism_client_id,
        client_secret=settings.photoprism_client_secret,
        username=settings.photoprism_username,
        password=settings.photoprism_password,
    )
    pp.authenticate()

    mistral = MistralClient(
        settings.mistral_api_key, model=settings.mistral_model, language=settings.output_language
    )

    processed = 0
    for photo in pp.iter_photos(batch_size=settings.batch_size, max_photos=settings.max_photos_per_run):
        if not needs_processing(photo, settings):
            continue

        uid = photo.get("UID")
        if not uid:
            continue

        try:
            image_bytes = _download_image(pp, photo)
            image_bytes = resize_image(
                image_bytes, settings.image_max_dimension, settings.image_jpeg_quality
            )
        except PhotoPrismError as exc:
            logger.warning("Skipping %s: could not download image: %s", uid, exc)
            continue

        try:
            analysis = mistral.analyze_image(image_bytes)
        except MistralError as exc:
            logger.warning("Skipping %s: Mistral analysis failed: %s", uid, exc)
            continue

        patch = build_patch(photo, analysis, settings)
        if not patch:
            continue

        if settings.dry_run:
            logger.info("[dry-run] Would update %s with: %s", uid, patch)
        else:
            try:
                pp.update_photo(uid, patch)
                logger.info("Updated photo %s: %s", uid, list(patch.keys()))
            except PhotoPrismError as exc:
                logger.error("Failed to update %s: %s", uid, exc)
                continue

        processed += 1

    logger.info("Run finished, %d photo(s) updated.", processed)
    return processed


def run_random_test(settings: Settings, write: bool = False) -> None:
    """Pick one random photo, run it through Mistral and print the result.

    Intended for manually verifying that PhotoPrism connectivity, image
    download and the Mistral prompt all work end to end, without touching
    your whole library. Nothing is written back unless `write=True`.
    """
    pp = PhotoPrismClient(
        settings.photoprism_url,
        client_id=settings.photoprism_client_id,
        client_secret=settings.photoprism_client_secret,
        username=settings.photoprism_username,
        password=settings.photoprism_password,
    )
    pp.authenticate()

    photo = pp.get_random_photo()
    if not photo:
        print("No photos found in this PhotoPrism library.")
        return

    uid = photo.get("UID")
    title = photo.get("Title") or uid
    print(f"Selected photo: {title} ({uid})")

    raw_bytes = _download_image(pp, photo)
    resized_bytes = resize_image(raw_bytes, settings.image_max_dimension, settings.image_jpeg_quality)
    print(
        f"Downloaded preview: {len(raw_bytes) / 1024:.0f} KB "
        f"-> resized to {len(resized_bytes) / 1024:.0f} KB "
        f"(max {settings.image_max_dimension}px, q={settings.image_jpeg_quality})"
    )

    mistral = MistralClient(
        settings.mistral_api_key, model=settings.mistral_model, language=settings.output_language
    )
    analysis = mistral.analyze_image(resized_bytes)

    print("\n--- Mistral analysis --------------------------------------")
    print(f"Description : {analysis.description}")
    print(f"Keywords    : {', '.join(analysis.keywords) if analysis.keywords else '-'}")
    print(f"Location    : {analysis.location_place or '-'} (confidence: {analysis.location_confidence})")
    print("-------------------------------------------------------------\n")

    print("--- Current PhotoPrism values --------------------------------")
    print(f"Description : {_current_description(photo) or '-'}")
    print(f"Keywords    : {', '.join(_current_keywords(photo)) or '-'}")
    print(f"Location    : Lat={photo.get('Lat')} Lng={photo.get('Lng')}")
    print("-------------------------------------------------------------\n")

    patch = build_patch(photo, analysis, settings)
    if not patch:
        print("Nothing to update (values already present, or below confidence threshold).")
        return

    if write:
        pp.update_photo(uid, patch)
        print(f"Saved to PhotoPrism: {list(patch.keys())}")
    else:
        print(f"Would update: {patch}")
        print("Re-run with --write to actually save this to PhotoPrism.")


def run_forever(settings: Settings) -> None:
    while True:
        try:
            run_once(settings)
        except Exception:
            logger.exception("Sync run failed")
        time.sleep(settings.sync_interval_seconds)
