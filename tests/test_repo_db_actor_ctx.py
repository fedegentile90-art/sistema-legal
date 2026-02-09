from repo_db import GestorCasosDB, _sanitize_ip


def test_resolve_actor_ctx_maps_ip_alias() -> None:
    gestor = GestorCasosDB()
    actor = gestor._resolve_actor_ctx(
        {
            "user_id": "u1",
            "user_name": "Jane",
            "role": "abogado",
            "ip": "127.0.0.1",
            "user_agent": "pytest",
            "request_id": "req-1",
        }
    )
    assert actor["ip"] == "127.0.0.1"
    assert actor["ip_address"] == "127.0.0.1"
    assert actor["role"] == "abogado"


def test_sanitize_ip_rejects_invalid() -> None:
    assert _sanitize_ip("10.0.0.1") == "10.0.0.1"
    assert _sanitize_ip("not-an-ip") is None
