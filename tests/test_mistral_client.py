import pytest

from pp_mistral.mistral_client import MistralError, parse_analysis


def test_parse_analysis_happy_path():
    content = (
        '{"description": "A mountain lake at sunset.", '
        '"keywords": ["Mountain", " Lake ", "Sunset"], '
        '"location_guess": {"confidence": "medium", "place": "Lake Louise, Canada"}}'
    )
    analysis = parse_analysis(content)
    assert analysis.description == "A mountain lake at sunset."
    assert analysis.keywords == ["mountain", "lake", "sunset"]
    assert analysis.location_confidence == "medium"
    assert analysis.location_place == "Lake Louise, Canada"


def test_parse_analysis_missing_location_defaults_to_none_confidence():
    analysis = parse_analysis('{"description": "A cat.", "keywords": ["cat"]}')
    assert analysis.location_confidence == "none"
    assert analysis.location_place is None


def test_parse_analysis_invalid_json_raises():
    with pytest.raises(MistralError):
        parse_analysis("not json")
