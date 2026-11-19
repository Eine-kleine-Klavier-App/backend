from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse

from piano_app.adapters.inbound.http.current_user import CurrentUserOptional
from piano_app.application.use_cases.score.playback.saved_score import SavedScorePlaybackService

from .responses import playback_map_payload, preview_carrier_payload


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

    @router.get("/preview/carriers/{carrier_id}", response_class=JSONResponse)
    async def preview_carrier(
        score_id: Annotated[str, Path()],
        carrier_id: Annotated[str, Path()],
        viewer_id: Annotated[str | None, Depends(current_user_optional)],
    ) -> JSONResponse:
        projection, version = await service.prepare_preview_carrier(
            score_id=score_id, viewer_id=viewer_id, carrier_id=carrier_id
        )
        return JSONResponse(
            content=preview_carrier_payload(
                projection=projection, carrier_id=carrier_id, version=version
            ),
            headers={"Cache-Control": "no-store"},
        )

    return router
