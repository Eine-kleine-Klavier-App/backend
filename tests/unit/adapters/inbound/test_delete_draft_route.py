from unittest.mock import Mock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.adapters.inbound.http.errors import register_exception_handlers
from piano_app.adapters.inbound.http.score.draft.router import build_draft_router
from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.errors import InvalidAccessTokenError
from piano_app.application.use_cases.score.draft.service import DraftService
from piano_app.domain.score.document import ScoreDocument


async def test_delete_route_owner_foreign_missing_and_unauthorized() -> None:
    storage = InMemoryDraftHistory()
    document = ScoreDocument.create(voices=[], staffs=[], measures=[])
    first = await storage.create(
        title="Delete", author_id="owner", ref_score_id="saved", document=document
    )
    second = await storage.create(
        title="Keep", author_id="owner", ref_score_id=None, document=document
    )
    auth = Mock()

    def authenticate_access_token(*, token: str | None) -> str:
        if token not in {"owner", "other"}:
            raise InvalidAccessTokenError()
        return token

    auth.authenticate_access_token.side_effect = authenticate_access_token
    app = FastAPI()
    register_exception_handlers(app=app)
    app.include_router(
        build_draft_router(
            service=DraftService(storage=storage, score_uow_factory=Mock()),
            current_user=CurrentUser(service=auth),
        )
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/drafts/{first.draft_id}"
        assert (await client.delete(path)).status_code == 401
        denied = await client.delete(path, headers={"Authorization": "Bearer other"})
        assert denied.status_code == 404
        assert await storage.get(draft_id=first.draft_id) is not None
        deleted = await client.delete(path, headers={"Authorization": "Bearer owner"})
        assert deleted.status_code == 204
        assert deleted.content == b""
        missing = await client.get(path, headers={"Authorization": "Bearer owner"})
        assert missing.status_code == 404
        repeated = await client.delete(path, headers={"Authorization": "Bearer owner"})
        assert repeated.status_code == 404
        listing = await client.get("/drafts", headers={"Authorization": "Bearer owner"})
        assert [item["draft_id"] for item in listing.json()] == [second.draft_id]
