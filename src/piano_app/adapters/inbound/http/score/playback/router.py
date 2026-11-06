from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Response
from fastapi.responses import JSONResponse

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.application.use_cases.score.playback import PlaybackService

from .requests import PlaybackRequest, PreviewRequest
from .responses import playback_map_payload, playback_response, preview_map_payload


def build_playback_router(*, service: PlaybackService, current_user: CurrentUser) -> APIRouter:
    router = APIRouter(prefix="/drafts/{draft_id}/playback", tags=["playback"])
    responses: dict[int | str, dict[str, Any]] = {
        200: {
            "description": (
                "Stereo s16le PCM; opt in to a framed JSON time map with "
                "Accept: application/vnd.piano.playback."
            ),
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                "application/vnd.piano.playback": {
                    "schema": {"type": "string", "format": "binary"}
                },
            },
        },
        204: {"description": "The requested range contains no audio frames."},
    }

    @router.get("/map", response_class=JSONResponse)
    async def playback_map(
        draft_id: Annotated[str, Path()],
        viewer_id: Annotated[str, Depends(current_user)],
    ) -> JSONResponse:
        projection, version = await service.prepare_map(draft_id=draft_id, viewer_id=viewer_id)
        return JSONResponse(
            content=playback_map_payload(projection=projection, version=version),
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/preview/map", response_class=JSONResponse)
    async def preview_map(
        draft_id: Annotated[str, Path()],
        viewer_id: Annotated[str, Depends(current_user)],
    ) -> JSONResponse:
        projections, version = await service.prepare_preview_map(
            draft_id=draft_id, viewer_id=viewer_id
        )
        return JSONResponse(
            content=preview_map_payload(projections=projections, version=version),
            headers={"Cache-Control": "no-store"},
        )

    @router.post("", response_class=Response, responses=responses)
    async def playback(
        draft_id: Annotated[str, Path()],
        viewer_id: Annotated[str, Depends(current_user)],
        request: PlaybackRequest,
        accept: Annotated[str | None, Header()] = None,
    ) -> Response:
        prepared = await service.prepare(
            draft_id=draft_id,
            viewer_id=viewer_id,
            start=request.start.to_domain(),
        )
        return await playback_response(
            prepared=prepared, include_map=accept == "application/vnd.piano.playback"
        )

    @router.post("/preview", response_class=Response, responses=responses)
    async def preview(
        draft_id: Annotated[str, Path()],
        viewer_id: Annotated[str, Depends(current_user)],
        request: PreviewRequest,
    ) -> Response:
        prepared = await service.prepare_preview(
            draft_id=draft_id,
            viewer_id=viewer_id,
            carrier_id=request.carrier_id,
            note_ids=None if request.note_ids is None else tuple(request.note_ids),
        )
        return await playback_response(prepared=prepared)

    return router
