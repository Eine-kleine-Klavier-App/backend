from typing import Annotated

from fastapi import APIRouter, Depends, Path

from piano_app.adapters.inbound.http import CurrentUser
from piano_app.adapters.inbound.http.score.save.requests import CreateScoreRequest
from piano_app.adapters.inbound.http.score.save.responses import ScoreSavedResponse
from piano_app.application.use_cases.score.manage.service import ScoreManageService

from .requests import ChangeScoreMetadataRequest, ChangeVisibilityRequest


def build_manage_router(*, service: ScoreManageService, current_user: CurrentUser) -> APIRouter:
    router: APIRouter = APIRouter(
        prefix="/scores/{score_id}",
        tags=["score-manage"],
    )

    @router.patch(path="", status_code=200)
    async def change_visibility(
        score_id: Annotated[str, Path(description="The score ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: ChangeVisibilityRequest,
    ) -> None:
        await service.update_visibility(
            score_id=score_id,
            actor_id=actor_id,
            is_public=request.is_public,
        )

    @router.patch(path="/metadata", status_code=200)
    async def change_metadata(
        score_id: Annotated[str, Path(description="The score ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: ChangeScoreMetadataRequest,
    ) -> None:
        await service.update_metadata(
            score_id=score_id, actor_id=actor_id, title=request.title, composer=request.composer
        )

    @router.post(path="/branches", status_code=201)
    async def create_branch(
        score_id: Annotated[str, Path(description="The saved parent score ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: CreateScoreRequest,
    ) -> ScoreSavedResponse:
        created_id = await service.create_branch_from_saved(
            score_id=score_id, actor_id=actor_id, command=request.to_command()
        )
        return ScoreSavedResponse.from_score_id(created_id)

    return router
