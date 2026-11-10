from collections.abc import Sequence

from piano_app.application.contracts.score import CreateScoreCommand
from piano_app.application.errors import ScoreNotFoundError
from piano_app.application.ports import CollectionPin, ScoreUoWFactory
from piano_app.application.ports.score import ScoreRepositoryNotFoundError
from piano_app.application.use_cases.score.shared import (
    require_readable_score,
    require_score_write_access,
)
from piano_app.domain.score import Score, ScoreMeta
from piano_app.domain.score.document import ScoreDocument


class ScoreManageService:
    def __init__(self, *, score_uow_factory: ScoreUoWFactory) -> None:
        self._score_uow_factory: ScoreUoWFactory = score_uow_factory

    async def update_visibility(self, *, score_id: str, actor_id: str, is_public: bool) -> None:
        async with self._score_uow_factory() as uow:
            meta: ScoreMeta = await require_score_write_access(
                score_repository=uow.score_repository,
                score_id=score_id,
                actor_id=actor_id,
            )
            try:
                await uow.score_repository.set_visibility(score_id=score_id, is_public=is_public)
            except ScoreRepositoryNotFoundError as error:
                raise ScoreNotFoundError(score_id=error.score_id) from error

            # Hiding a score must not take it away from people who saved it: each holder gets a
            # private copy of the version they pinned. Only public scores can be pinned by others,
            # so this finds nothing for a score that was already private.
            if not is_public:
                pins: Sequence[
                    CollectionPin
                ] = await uow.collection_repository.pins_of_other_owners(
                    score_id=score_id, owner_id=actor_id
                )
                copies: dict[tuple[str, str], str] = {}
                for pin in pins:
                    key: tuple[str, str] = (pin.owner_id, pin.score_content_id)
                    if key not in copies:
                        document: (
                            ScoreDocument | None
                        ) = await uow.score_repository.get_content_document(
                            content_id=pin.score_content_id
                        )
                        if document is None:
                            raise RuntimeError(f"Score {score_id!r} lost a pinned version.")
                        copy: Score = await uow.score_repository.create(
                            title=meta.title,
                            composer=meta.composer,
                            author_id=pin.owner_id,
                            derived_from_id=score_id,
                            document=document,
                        )
                        copies[key] = copy.id
                    await uow.collection_repository.repin(item_id=pin.item_id, score_id=copies[key])
            await uow.commit()

    async def delete(self, *, score_id: str) -> None:
        pass

    async def update_metadata(
        self, *, score_id: str, actor_id: str, title: str, composer: str | None
    ) -> None:
        async with self._score_uow_factory() as uow:
            await require_score_write_access(
                score_repository=uow.score_repository, score_id=score_id, actor_id=actor_id
            )
            try:
                await uow.score_repository.set_title(score_id=score_id, title=title)
                await uow.score_repository.set_composer(score_id=score_id, composer=composer)
            except ScoreRepositoryNotFoundError as error:
                raise ScoreNotFoundError(score_id=error.score_id) from error
            await uow.commit()

    async def create_branch_from_saved(
        self, *, score_id: str, actor_id: str, command: CreateScoreCommand
    ) -> str:
        async with self._score_uow_factory() as uow:
            parent = await require_readable_score(
                score_repository=uow.score_repository, score_id=score_id, viewer_id=actor_id
            )
            created = await uow.score_repository.create(
                title=command.title,
                composer=command.composer,
                author_id=actor_id,
                derived_from_id=None if parent.meta.is_frozen else parent.id,
                document=parent.document,
                is_public=command.is_public,
            )
            await uow.commit()
        return created.id
