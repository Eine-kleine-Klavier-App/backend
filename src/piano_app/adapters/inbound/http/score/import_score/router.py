from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.application.errors import ImportTooLargeError
from piano_app.application.use_cases.score.import_score.jobs import ImportJob
from piano_app.application.use_cases.score.import_score.service import ImportService

from .responses import ImportJobResponse

_FILENAME = Annotated[
    str, Query(min_length=1, max_length=255, description="The name of the uploaded file")
]


async def _body_of(*, request: Request, limit: int) -> bytes:
    declared: str | None = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise ImportTooLargeError(limit=limit)

    body: bytearray = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise ImportTooLargeError(limit=limit)

    return bytes(body)


def build_import_router(
    *, service: ImportService, current_user: CurrentUser, max_upload_bytes: int
) -> APIRouter:
    """Routes that take a score file as the request body and answer with a job: an import makes
    a draft from it, a comparison tells how a draft differs from it. The job's state is asked
    for by its id."""
    router: APIRouter = APIRouter(tags=["import"])

    @router.post(path="/imports", status_code=202)
    async def start_import(
        request: Request,
        response: Response,
        actor_id: Annotated[str, Depends(current_user)],
        filename: _FILENAME,
    ) -> ImportJobResponse:
        data: bytes = await _body_of(request=request, limit=max_upload_bytes)
        job: ImportJob = await service.start(actor_id=actor_id, filename=filename, data=data)
        response.headers["Location"] = f"/imports/{job.job_id}"
        return ImportJobResponse.from_job(job)

    @router.post(path="/drafts/{draft_id}/compare", status_code=202)
    async def start_comparison(
        request: Request,
        response: Response,
        draft_id: Annotated[str, Path(description="The draft to compare with the file")],
        actor_id: Annotated[str, Depends(current_user)],
        filename: _FILENAME,
    ) -> ImportJobResponse:
        data: bytes = await _body_of(request=request, limit=max_upload_bytes)
        job: ImportJob = await service.compare(
            actor_id=actor_id, draft_id=draft_id, filename=filename, data=data
        )
        response.headers["Location"] = f"/imports/{job.job_id}"
        return ImportJobResponse.from_job(job)

    @router.get(path="/imports/{job_id}", status_code=200)
    async def get_import(
        job_id: Annotated[str, Path(description="The job's id")],
        actor_id: Annotated[str, Depends(current_user)],
    ) -> ImportJobResponse:
        return ImportJobResponse.from_job(service.state(job_id=job_id, actor_id=actor_id))

    return router
