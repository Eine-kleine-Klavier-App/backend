import asyncio
from typing import Any

from piano_app.adapters.inbound.http.score.sync import measure_sync_payload
from piano_app.application.ports.score import VersionedDraftDocument
from piano_app.application.use_cases.score.shared import ScoreState, ScoreView, state_sync
from piano_app.application.use_cases.score.shared.draft_history import DraftHistoryService


class ClientView:
    """The view of one draft as a client holds it, measure by measure, the way the frontend keeps
    it: the draft whole first, then every response by measure laid over it."""

    def __init__(self, *, storage: DraftHistoryService, draft_id: str) -> None:
        versioned: VersionedDraftDocument | None = asyncio.run(storage.get(draft_id=draft_id))
        assert versioned is not None
        state: ScoreState = ScoreState(
            document=versioned.document,
            view=ScoreView(document=versioned.document),
            version=versioned.version,
            step=None,
        )
        self._version: int | None = None
        self._header: dict[str, Any] = {}
        self._shares: dict[str, dict[str, Any]] = {}
        self.apply(sync=measure_sync_payload(sync=state_sync(state=state)))

    def apply(self, *, sync: dict[str, Any]) -> dict[str, Any]:
        """Lays a response over the view held and gives the whole view put together again."""
        if sync["from_version"] is None:
            self._shares.clear()
        else:
            assert sync["from_version"] == self._version, (sync["from_version"], self._version)
        if sync["header"] is not None:
            self._header = sync["header"]
        for measure_id in sync["removed"]:
            del self._shares[measure_id]
        for share in sync["measures"]:
            self._shares[share["measure"]["id"]] = share
        self._version = sync["to_version"]

        return self._view()

    def _view(self) -> dict[str, Any]:
        header: dict[str, Any] = self._header
        shares: list[dict[str, Any]] = [
            self._shares[measure_id] for measure_id in header["measure_ids"]
        ]
        roots: dict[str, list[str]] = {voice_id: [] for voice_id in header["voice_ids"]}
        for share in shares:
            for root in share["voice_roots"]:
                roots[root["voice_id"]].extend(root["rhythmic_container_ids"])

        presentation: dict[str, list[Any]] = {
            kind: list(rows) for kind, rows in header["presentation"].items()
        }
        for share in shares:
            for kind, rows in share["presentation"].items():
                presentation[kind].extend(rows)

        def joined(key: str) -> list[Any]:
            return [row for share in shares for row in share[key]]

        return {
            "music_revision": header["music_revision"],
            "presentation": presentation,
            "presentation_capabilities": [
                *header["presentation_capabilities"],
                *joined("presentation_capabilities"),
            ],
            "insertion_spaces": joined("insertion_spaces"),
            "staffs": header["staffs"],
            "measures": [share["measure"] for share in shares],
            "voices": [
                {"id": voice_id, "rhythmic_container_ids": container_ids}
                for voice_id, container_ids in roots.items()
            ],
            "rhythmic_containers": joined("rhythmic_containers"),
            "carriers": joined("carriers"),
            "items": joined("items"),
            "relations": joined("relations"),
            "contexts": joined("contexts"),
        }
