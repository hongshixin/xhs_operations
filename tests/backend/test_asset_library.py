from pathlib import Path

from backend.app.api.files import _upload_title, find_duplicate_upload


def test_duplicate_upload_detects_same_bytes_for_same_user(tmp_path: Path):
    existing = tmp_path / "xhs-upload-u7-original.png"
    existing.write_bytes(b"same picture")
    (tmp_path / "xhs-upload-u8-other.png").write_bytes(b"same picture")

    assert find_duplicate_upload(tmp_path, 7, b"same picture") == existing
    assert find_duplicate_upload(tmp_path, 8, b"different picture") is None


def test_duplicate_upload_ignores_different_bytes_with_same_size(tmp_path: Path):
    (tmp_path / "xhs-upload-u7-original.png").write_bytes(b"abc")

    assert find_duplicate_upload(tmp_path, 7, b"xyz") is None


def test_uploaded_asset_keeps_searchable_original_name(tmp_path: Path):
    file = tmp_path / "xhs-upload-u7-random.png"
    file.write_bytes(b"picture")
    file.with_suffix(".png.json").write_text('{"original_name":"封面参考.png"}', encoding="utf-8")

    assert _upload_title(file) == "封面参考.png"
