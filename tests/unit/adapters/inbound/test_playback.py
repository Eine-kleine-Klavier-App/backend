from fastapi.testclient import TestClient


def test_bootstrap_registers_the_map_routes_and_no_audio_routes() -> None:
    from pydantic import SecretStr

    from piano_app.bootstrap.container import build_app
    from piano_app.bootstrap.settings.models import Settings

    app = build_app(
        settings=Settings(
            DATABASE_URL="postgresql+asyncpg://test:test@127.0.0.1/test",
            JWT_SECRET=SecretStr("t" * 64),
            GOOGLE_CLIENT_IDS=("test-client",),
            CORS_ORIGINS=("https://piano.test",),
        )
    )
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/drafts/{draft_id}/playback/map" not in paths
    assert "/drafts/{draft_id}/playback/preview/carriers/{carrier_id}" not in paths
    assert "/drafts/{draft_id}/playback/preview/map" not in paths
    assert "/drafts/{draft_id}/playback" not in paths
    assert "/drafts/{draft_id}/playback/preview" not in paths
