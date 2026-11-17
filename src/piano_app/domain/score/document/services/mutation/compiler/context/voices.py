from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import VoicesScoped
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    AddContextVoiceIntent,
    RemoveContextVoiceIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    refuse_initial_context,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    UpdateContextVoicesRequest,
)


class AddContextVoiceCompiler:
    """Compiles one more voice for a context into one update request; whether the kind allows
    it over the context's span is decided where the request is analyzed."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: AddContextVoiceIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.context_id, intent.voice_id),
        )
        context: VoicesScoped = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.context_id,
            expected=VoicesScoped,
        )
        voice: Voice = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.voice_id,
            expected=Voice,
        )
        if voice in context.voices:
            raise MutationRejectedError("The voice already belongs to this context.")

        return [UpdateContextVoicesRequest(target=context, voices=(*context.voices, voice))]


class RemoveContextVoiceCompiler:
    """Compiles one voice leaving a context into one update request. A context keeps at least
    one voice, and the voice of an initial context loses it as little as it could be deleted."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: RemoveContextVoiceIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.context_id, intent.voice_id),
        )
        context: VoicesScoped = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.context_id,
            expected=VoicesScoped,
        )
        voice: Voice = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.voice_id,
            expected=Voice,
        )
        if voice not in context.voices:
            raise MutationRejectedError("The voice does not belong to this context.")

        remaining: tuple[Voice, ...] = tuple(
            member for member in context.voices if member is not voice
        )
        if not remaining:
            raise MutationRejectedError("A context keeps at least one voice.")

        refuse_initial_context(document=document, entity=context)

        return [UpdateContextVoicesRequest(target=context, voices=remaining)]
