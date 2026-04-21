from pathlib import Path

from shoplift_detector.app.services.ai_service import (
    BYTE_TRACK_CONFIG_PATH,
    ShopliftDetector,
)


def _read_simple_yaml(path: Path) -> dict[str, object]:
    data = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value in {"true", "false"}:
            parsed_value = value == "true"
        elif "." in value:
            parsed_value = float(value)
        elif value.isdigit():
            parsed_value = int(value)
        else:
            parsed_value = value
        data[key.strip()] = parsed_value
    return data


def test_bytetrack_config_file_has_required_thresholds():
    config_path = Path(BYTE_TRACK_CONFIG_PATH)
    assert config_path.exists()

    data = _read_simple_yaml(config_path)

    assert data["tracker_type"] == "bytetrack"
    assert data["track_high_thresh"] == 0.6
    assert data["track_buffer"] == 60
    assert data["match_thresh"] == 0.8


def test_shoplift_detector_resolves_bytetrack_config_path():
    config_path = Path(ShopliftDetector._get_tracker_config_path())

    assert config_path == BYTE_TRACK_CONFIG_PATH
    assert config_path.name == "bytetrack.yaml"
