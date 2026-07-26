from pp_mistral.config import Settings
from pp_mistral.mistral_client import PhotoAnalysis
from pp_mistral.sync import GEO_REVIEW_KEYWORD, build_patch, needs_processing


def make_settings(**overrides):
    base = dict(
        photoprism_url="http://pp",
        photoprism_client_id="id",
        photoprism_client_secret="secret",
        photoprism_username=None,
        photoprism_password=None,
        mistral_api_key="key",
        mistral_model="pixtral-large-latest",
        enable_description=True,
        enable_keywords=True,
        enable_geolocation=True,
        overwrite_existing=False,
        batch_size=10,
        max_photos_per_run=0,
        sync_interval_seconds=60,
        dry_run=False,
        geocode_user_agent="test-agent",
    )
    base.update(overrides)
    return Settings(**base)


def test_needs_processing_skips_complete_photo():
    settings = make_settings()
    photo = {
        "Description": "A cat",
        "Details": {"Keywords": "cat, sofa"},
        "Lat": 48.1,
        "Lng": 11.5,
    }
    assert needs_processing(photo, settings) is False


def test_needs_processing_flags_missing_description():
    settings = make_settings()
    photo = {"Details": {"Keywords": "cat"}, "Lat": 1, "Lng": 1}
    assert needs_processing(photo, settings) is True


def test_build_patch_fills_description_and_keywords_without_overwriting():
    settings = make_settings(enable_geolocation=False)
    photo = {"Details": {"Keywords": "cat"}}
    analysis = PhotoAnalysis(description="A cat on a sofa", keywords=["cat", "sofa", "indoor"])
    patch = build_patch(photo, analysis, settings)
    assert patch["Description"] == "A cat on a sofa"
    assert patch["Details"]["Keywords"] == "cat, sofa, indoor"


def test_build_patch_does_not_overwrite_existing_description():
    settings = make_settings(enable_geolocation=False)
    photo = {"Description": "Existing", "Details": {"Keywords": "cat"}}
    analysis = PhotoAnalysis(description="New description", keywords=["dog"])
    patch = build_patch(photo, analysis, settings)
    assert "Description" not in patch


def test_build_patch_skips_low_confidence_location():
    settings = make_settings()
    photo = {}
    analysis = PhotoAnalysis(location_confidence="low", location_place="Somewhere")
    patch = build_patch(photo, analysis, settings)
    assert "Lat" not in patch


def test_build_patch_geocodes_high_confidence_location(monkeypatch):
    import pp_mistral.sync as sync_module

    monkeypatch.setattr(sync_module, "geocode_place", lambda place, ua: (48.8584, 2.2945))
    settings = make_settings(enable_description=False, enable_keywords=False)
    photo = {}
    analysis = PhotoAnalysis(location_confidence="high", location_place="Eiffel Tower, Paris")
    patch = build_patch(photo, analysis, settings)
    assert patch["Lat"] == 48.8584
    assert patch["Lng"] == 2.2945
    assert GEO_REVIEW_KEYWORD in patch["Details"]["Keywords"]


def test_build_patch_skips_geolocation_when_already_present():
    settings = make_settings(enable_description=False, enable_keywords=False)
    photo = {"Lat": 1.0, "Lng": 1.0}
    analysis = PhotoAnalysis(location_confidence="high", location_place="Eiffel Tower, Paris")
    patch = build_patch(photo, analysis, settings)
    assert patch == {}
