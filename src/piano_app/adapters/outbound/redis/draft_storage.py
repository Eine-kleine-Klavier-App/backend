import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

from piano_app.application.ports.score import (
    DocumentRecord,
    DraftMeta,
    DraftStoreNotFoundError,
    DraftStoreVersionConflictError,
    RecordChange,
    StoredDraft,
)

# Redis hashes have no native scalar null. The `score` field is required so
# scripts can distinguish a complete draft with no referenced score from a
# corrupted meta hash missing the field. Referenced score ids are generated
# UUIDs, so they cannot collide with this sentinel.
_NO_SCORE_SENTINEL: Final[str] = "none"

_SCRIPTS_DIR: Final[Path] = Path(__file__).parent / "scripts"


def _load(name: str) -> str:
    return (_SCRIPTS_DIR / name).read_text()


class RedisDraftStorage:
    """Redis-backed draft storage.

    Each draft uses four keys: its metadata (``draft:{id}:meta``), its version
    (``draft:{id}:state``), its record (``draft:{id}:record``) and its history, the changes and
    the cursor (``draft:{id}:history``). Lua scripts update them atomically, a write only on the
    version the writer read.

    ``remember_deleted`` makes a deleted draft id unrestorable (``hydrate`` refuses it), for the
    hot tier of a tiered store, where a late read from cold must not bring a deleted draft back.
    """

    def __init__(
        self,
        *,
        client: Redis,
        ttl_seconds: int = 300,
        remember_deleted: bool = False,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError(f"ttl_seconds must be >= 1, got {ttl_seconds!r}.")

        self._client: Redis = client
        # a draft is automatically deleted from Redis after specified TTL
        # (get() is read-only and does not refresh the TTL)
        self._ttl_seconds: Final[int] = ttl_seconds
        self._remember_deleted: Final[bool] = remember_deleted

        self._create_script: AsyncScript = client.register_script(_load("create.lua"))
        self._get_script: AsyncScript = client.register_script(_load("get.lua"))
        self._put_script: AsyncScript = client.register_script(_load("put.lua"))
        self._delete_script: AsyncScript = client.register_script(_load("delete.lua"))
        self._hydrate_script: AsyncScript = client.register_script(_load("hydrate.lua"))
        self._list_by_author_script: AsyncScript = client.register_script(
            _load("list_by_author.lua")
        )

    # TODO consider adding retries if ids collide
    async def create(
        self,
        *,
        title: str,
        author_id: str,
        ref_score_id: str | None,
        record: DocumentRecord,
    ) -> StoredDraft:
        draft_id: str = str(uuid4())
        meta: DraftMeta = DraftMeta(
            draft_id=draft_id,
            title=title,
            author_id=author_id,
            ref_score_id=ref_score_id,
            updated_at=datetime.now(UTC).replace(microsecond=0),
        )
        response: list[bytes | str | int] = await self._create_script(
            keys=[
                *self._draft_keys(draft_id=draft_id),
                self._author_drafts_key(author_id=author_id),
            ],
            args=[
                draft_id,
                author_id,
                title,
                self._encode_ref_score_id(ref_score_id),
                json.dumps(record),
                self._encode_history(changes=(), cursor=0),
                self._encode_datetime(meta.updated_at),
                self._ttl_seconds,
            ],
        )

        code: str = self._to_str(response[0])
        if code != "ok":
            raise RuntimeError(f"Unexpected Redis create response: {code!r}, {response[1:]!r}.")

        return StoredDraft(meta=meta, version=0, record=record, changes=(), cursor=0)

    async def get(self, *, draft_id: str) -> StoredDraft | None:
        response: list[bytes | str | int] = await self._get_script(
            keys=self._draft_keys(draft_id=draft_id)
        )

        code: str = self._to_str(response[0])
        body: list[bytes | str | int] = response[1:]
        match code:
            case "ok":
                record, history, version, author, title, updated_at, score = body
                changes, cursor = self._decode_history(history)
                return StoredDraft(
                    meta=DraftMeta(
                        draft_id=draft_id,
                        title=self._to_str(title),
                        author_id=self._to_str(author),
                        ref_score_id=self._decode_ref_score_id(score),
                        updated_at=self._decode_datetime(updated_at),
                    ),
                    version=int(self._to_str(version)),
                    record=json.loads(self._to_str(record)),
                    changes=changes,
                    cursor=cursor,
                )
            case "not_found":
                return None
            case _:
                raise RuntimeError(f"Unexpected Redis get response: {code!r}, {body!r}.")

    async def put(self, *, draft: StoredDraft, expected_version: int) -> None:
        draft_id: str = draft.meta.draft_id
        response: list[bytes | str | int] = await self._put_script(
            keys=self._draft_keys(draft_id=draft_id),
            args=[
                expected_version,
                draft.version,
                json.dumps(draft.record),
                self._encode_history(changes=draft.changes, cursor=draft.cursor),
                self._encode_datetime(draft.meta.updated_at),
                self._ttl_seconds,
            ],
        )

        code: str = self._to_str(response[0])
        match code:
            case "ok":
                return
            case "not_found":
                raise DraftStoreNotFoundError(draft_id=draft_id)
            case "conflict":
                raise DraftStoreVersionConflictError(draft_id=draft_id, version=expected_version)
            case _:
                raise RuntimeError(f"Unexpected Redis put response: {code!r}, {response[1:]!r}.")

    async def hydrate(self, *, draft: StoredDraft) -> None:
        """Puts back a draft the tier lost. Does nothing if it holds the draft already or if the
        draft was deleted here."""
        draft_id: str = draft.meta.draft_id
        response: list[bytes | str | int] = await self._hydrate_script(
            keys=[*self._draft_keys(draft_id=draft_id), self._deleted_key(draft_id=draft_id)],
            args=[
                draft.version,
                draft.meta.author_id,
                draft.meta.title,
                self._encode_ref_score_id(draft.meta.ref_score_id),
                self._encode_datetime(draft.meta.updated_at),
                self._ttl_seconds,
                json.dumps(draft.record),
                self._encode_history(changes=draft.changes, cursor=draft.cursor),
            ],
        )

        code: str = self._to_str(response[0])
        if code not in ("ok", "exists", "deleted"):
            raise RuntimeError(f"Unexpected Redis hydrate response: {code!r}, {response[1:]!r}.")

    async def delete(self, *, draft_id: str) -> None:
        author: bytes | str | None = await self._client.hget(
            self._meta_key(draft_id=draft_id), "author"
        )
        keys: list[str] = [
            *self._draft_keys(draft_id=draft_id),
            self._deleted_key(draft_id=draft_id),
        ]
        if author is not None:
            keys.append(self._author_drafts_key(author_id=self._to_str(author)))

        response: list[bytes | str | int] = await self._delete_script(
            keys=keys, args=[draft_id, "1" if self._remember_deleted else "0"]
        )
        if self._to_str(response[0]) != "ok":
            raise RuntimeError(f"Unexpected Redis delete response: {response!r}.")

    # SMEMBERS runs here, not in the script: Python builds the keys, so it needs
    # the ids first. draft_ids go into ARGV too, since deriving them from key
    # strings inside the script would tie it to the key format again.
    async def list_by_author(self, *, author_id: str) -> Sequence[DraftMeta]:
        author_drafts_key: str = self._author_drafts_key(author_id=author_id)
        raw_draft_ids: set[bytes | str] = await self._client.smembers(author_drafts_key)
        draft_ids: list[str] = [self._to_str(value) for value in raw_draft_ids]

        if not draft_ids:
            return []

        keys: list[str] = [author_drafts_key]
        for draft_id in draft_ids:
            keys.extend(self._draft_keys(draft_id=draft_id))

        response: list[bytes | str | int] = await self._list_by_author_script(
            keys=keys, args=draft_ids
        )

        code: str = self._to_str(response[0])
        if code != "ok":
            raise RuntimeError(
                f"Unexpected Redis list_by_author response: {code!r}, {response[1:]!r}."
            )

        # the script's rows, flat: id, author, title, updated_at, score
        row_size: int = 5
        body: list[bytes | str | int] = response[1:]
        metas: list[DraftMeta] = []
        for i in range(0, len(body), row_size):
            listed_id, author, title, updated_at, score = body[i : i + row_size]
            metas.append(
                DraftMeta(
                    draft_id=self._to_str(listed_id),
                    title=self._to_str(title),
                    author_id=self._to_str(author),
                    ref_score_id=self._decode_ref_score_id(score),
                    updated_at=self._decode_datetime(updated_at),
                )
            )

        return sorted(metas, key=lambda meta: (meta.updated_at, meta.draft_id), reverse=True)

    async def aclose(self) -> None:
        """Closes the underlying Redis connection pool. Call on app shutdown."""
        await self._client.aclose()

    # the method is used to guarantee independence from the config of Redis
    # even if decode is set to False, this method guarantees that the result is always a string
    @staticmethod
    def _to_str(value: bytes | str | int) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)

    @staticmethod
    def _encode_history(*, changes: Sequence[RecordChange], cursor: int) -> str:
        return json.dumps({"changes": list(changes), "cursor": cursor})

    def _decode_history(self, value: bytes | str | int) -> tuple[tuple[RecordChange, ...], int]:
        history: dict[str, Any] = json.loads(self._to_str(value))
        return tuple(history["changes"]), history["cursor"]

    @staticmethod
    def _encode_ref_score_id(ref_score_id: str | None) -> str:
        return ref_score_id if ref_score_id is not None else _NO_SCORE_SENTINEL

    def _decode_ref_score_id(self, value: bytes | str | int) -> str | None:
        raw: str = self._to_str(value)
        return raw if raw != _NO_SCORE_SENTINEL else None

    @staticmethod
    def _encode_datetime(value: datetime) -> str:
        return str(int(value.timestamp()))

    def _decode_datetime(self, value: bytes | str | int) -> datetime:
        return datetime.fromtimestamp(int(self._to_str(value)), tz=UTC)

    def _draft_keys(self, *, draft_id: str) -> list[str]:
        """The four keys of a draft, in the order the scripts take them."""
        return [
            self._meta_key(draft_id=draft_id),
            f"draft:{draft_id}:state",
            f"draft:{draft_id}:record",
            f"draft:{draft_id}:history",
        ]

    @staticmethod
    def _meta_key(*, draft_id: str) -> str:
        return f"draft:{draft_id}:meta"

    @staticmethod
    def _deleted_key(*, draft_id: str) -> str:
        return f"draft:{draft_id}:deleted"

    @staticmethod
    def _author_drafts_key(*, author_id: str) -> str:
        return f"drafts:{author_id}"
