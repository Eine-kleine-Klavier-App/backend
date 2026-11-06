from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from fastapi.responses import JSONResponse

from piano_app.adapters.inbound.http.current_user import CurrentUserOptional
from piano_app.application.use_cases.score.playback.saved_score import SavedScorePlaybackService

from .requests import PlaybackRequest
from .responses import playback_map_payload, playback_response, preview_map_payload


def build_saved_playback_router(
    *, service: SavedScorePlaybackService, current_user_optional: CurrentUserOptional
) -> APIRouter:
    router = APIRouter(prefix="/scores/{score_id}/playback", tags=["score-playback"])

    @router.get("/map", response_class=JSONResponse)
    async def playback_map(
        score_id: Annotated[str, Path()],
        viewer_id: Annotated[str | None, Depends(current_user_optional)],
    ) -> JSONResponse:
        projection, version = await service.prepare_map(score_id=score_id, viewer_id=viewer_id)
        return JSONResponse(
            content=playback_map_payload(projection=projection, version=version),
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/preview/map", response_class=JSONResponse)
    async def preview_map(
        score_id: Annotated[str, Path()],
        viewer_id: Annotated[str | None, Depends(current_user_optional)],
    ) -> JSONResponse:
        projections, version = await service.prepare_preview_map(
            score_id=score_id, viewer_id=viewer_id
        )
        return JSONResponse(
            content=preview_map_payload(projections=projections, version=version),
            headers={"Cache-Control": "no-store"},
        )

    @router.post("", response_class=Response)
    async def playback(
        score_id: Annotated[str, Path()],
        viewer_id: Annotated[str | None, Depends(current_user_optional)],
        request: PlaybackRequest,
    ) -> Response:
        prepared = await service.prepare(
            score_id=score_id, viewer_id=viewer_id, start=request.start.to_domain()
        )
        return await playback_response(prepared=prepared, version_header="X-Score-Version")

    return router
