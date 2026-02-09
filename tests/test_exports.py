from exports import build_export_metadata, payload_to_json_bytes


def test_payload_to_json_bytes_is_deterministic() -> None:
    payload_a = {"b": 2, "a": 1}
    payload_b = {"a": 1, "b": 2}
    bytes_a = payload_to_json_bytes(payload_a)
    bytes_b = payload_to_json_bytes(payload_b)
    assert bytes_a == bytes_b


def test_build_export_metadata_checksum() -> None:
    content = b"legal-export-content"
    meta = build_export_metadata("cases_csv", content)
    assert meta["export_name"] == "cases_csv"
    assert meta["size_bytes"] == len(content)
    assert len(meta["sha256"]) == 64
