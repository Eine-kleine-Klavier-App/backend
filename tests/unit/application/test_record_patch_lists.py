import json
import random

import pytest

from piano_app.application.ports.score import DocumentRecord, RecordChange
from piano_app.application.use_cases.score.shared.record_patch import apply_change, diff_records

# A field that is a list of ids is changed by what left it, with the place it had, and what came
# into it, with the place it has. Whatever two such lists are, applying the change to one gives the
# other and taking it back gives the first, and what is written stays small when little moved.


def _ids(count: int) -> list[str]:
    return [f"id{number}" for number in range(count)]


def _of(items: list[str]) -> DocumentRecord:
    return {"order": items, "tables": {}}


def _change(*, before: list[str], after: list[str]) -> RecordChange:
    return diff_records(before=_of(before), after=_of(after))


def _round_trips(*, before: list[str], after: list[str]) -> RecordChange:
    """The change between two lists, checked in both directions and after a trip through JSON
    with the keys sorted, which is how the store may hand it back."""
    change: RecordChange = _change(before=before, after=after)
    stored: RecordChange = json.loads(json.dumps(change, sort_keys=True))

    for candidate in (change, stored):
        assert apply_change(record=_of(before), change=candidate, forward=True)["order"] == after
        assert apply_change(record=_of(after), change=candidate, forward=False)["order"] == before

    return change


@pytest.mark.unit
def test_an_id_that_came_in_is_written_with_its_place() -> None:
    change: RecordChange = _round_trips(before=["a", "b", "c"], after=["a", "x", "b", "c"])

    assert change["fields"]["order"] == {"removed": [], "inserted": [[1, "x"]]}


@pytest.mark.unit
def test_an_id_that_left_is_written_with_the_place_it_had() -> None:
    change: RecordChange = _round_trips(before=["a", "b", "c"], after=["a", "c"])

    assert change["fields"]["order"] == {"removed": [[1, "b"]], "inserted": []}


@pytest.mark.unit
def test_ids_that_left_apart_and_together_keep_their_own_places() -> None:
    before: list[str] = _ids(12)
    after: list[str] = [item for index, item in enumerate(before) if index not in (2, 7, 8, 9)]

    change: RecordChange = _round_trips(before=before, after=after)

    assert change["fields"]["order"]["removed"] == [[2, "id2"], [7, "id7"], [8, "id8"], [9, "id9"]]
    assert change["fields"]["order"]["inserted"] == []


@pytest.mark.unit
def test_an_id_that_moved_is_written_as_leaving_and_coming_in() -> None:
    change: RecordChange = _round_trips(before=["a", "b", "c", "d"], after=["d", "a", "b", "c"])

    assert change["fields"]["order"] == {"removed": [[3, "d"]], "inserted": [[0, "d"]]}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("before", "after"),
    [
        (["a", "b", "c"], ["c", "b", "a"]),
        (["a", "b", "c", "d", "e"], ["b", "a", "d", "c", "e"]),
        (["a"], ["b"]),
        ([], ["a", "b"]),
        (["a", "b"], []),
        ([], []),
        (["a", "b", "c"], ["x", "y", "z"]),
        (["a", "b", "c"], ["c", "x", "a"]),
        (["a", "b", "c", "d"], ["a", "b", "c", "d", "e", "f"]),
        (["a", "b", "c", "d"], ["x", "a", "b", "c", "d"]),
    ],
)
def test_the_edge_cases_of_two_lists_round_trip(before: list[str], after: list[str]) -> None:
    _round_trips(before=before, after=after)


@pytest.mark.unit
@pytest.mark.parametrize("seed", range(40))
def test_any_two_lists_of_ids_round_trip(seed: int) -> None:
    rng: random.Random = random.Random(seed)
    pool: list[str] = _ids(rng.randint(1, 60))
    for _ in range(25):
        before: list[str] = rng.sample(pool, rng.randint(0, len(pool)))
        after: list[str] = rng.sample(pool, rng.randint(0, len(pool)))
        _round_trips(before=before, after=after)


@pytest.mark.unit
@pytest.mark.parametrize("seed", range(20))
def test_a_few_changes_to_a_long_list_round_trip_and_stay_small(seed: int) -> None:
    rng: random.Random = random.Random(seed)
    before: list[str] = _ids(800)
    after: list[str] = list(before)
    for _ in range(rng.randint(1, 8)):
        kind: int = rng.randint(0, 2)
        if kind == 0 and after:
            del after[rng.randrange(len(after))]
        elif kind == 1:
            after.insert(rng.randint(0, len(after)), f"new{rng.randint(0, 10**9)}")
        elif after:
            item: str = after.pop(rng.randrange(len(after)))
            after.insert(rng.randint(0, len(after)), item)

    change: RecordChange = _round_trips(before=before, after=after)

    if before != after:
        assert len(json.dumps(change)) < 600
        assert len(json.dumps(change)) < len(json.dumps([before, after])) // 20


@pytest.mark.unit
def test_taking_six_relations_out_of_seven_hundred_costs_a_few_hundred_bytes() -> None:
    before: list[str] = [f"{number:032x}" for number in range(777)]
    gone: tuple[int, ...] = (72, 78, 79, 80, 81, 82)
    after: list[str] = [item for index, item in enumerate(before) if index not in gone]

    change: RecordChange = _round_trips(before=before, after=after)

    assert [place for place, _ in change["fields"]["order"]["removed"]] == list(gone)
    assert len(json.dumps(change)) < 400
    assert len(json.dumps([before, after])) > 50_000


@pytest.mark.unit
def test_a_chain_of_changes_walks_forward_and_back_to_every_list_in_it() -> None:
    rng: random.Random = random.Random(7)
    pool: list[str] = _ids(40)
    lists: list[list[str]] = [rng.sample(pool, rng.randint(0, 40)) for _ in range(30)]
    changes: list[RecordChange] = [
        _change(before=lists[index], after=lists[index + 1]) for index in range(len(lists) - 1)
    ]

    record: DocumentRecord = _of(lists[0])
    for index, change in enumerate(changes):
        record = apply_change(record=record, change=change, forward=True)
        assert record["order"] == lists[index + 1]

    for index in reversed(range(len(changes))):
        record = apply_change(record=record, change=changes[index], forward=False)
        assert record["order"] == lists[index]


@pytest.mark.unit
def test_applying_a_list_change_leaves_the_list_it_was_given_as_it_was() -> None:
    before: list[str] = ["a", "b", "c"]
    record: DocumentRecord = _of(before)

    apply_change(record=record, change=_change(before=before, after=["a", "x"]), forward=True)

    assert before == ["a", "b", "c"]
    assert record["order"] is before


@pytest.mark.unit
def test_a_list_that_is_not_ids_or_holds_one_twice_is_written_whole() -> None:
    for before, after in (
        (["a", "a"], ["a"]),
        ([1, 2], [2, 1]),
        (["a", 1], ["a"]),
        (["a"], ["a", "a"]),
    ):
        change: RecordChange = diff_records(
            before={"order": before, "tables": {}}, after={"order": after, "tables": {}}
        )

        assert change["fields"]["order"] == [before, after]
        assert (
            apply_change(record={"order": before, "tables": {}}, change=change, forward=True)[
                "order"
            ]
            == after
        )


@pytest.mark.unit
def test_a_list_that_appears_or_goes_is_written_whole() -> None:
    appears: RecordChange = diff_records(before={"tables": {}}, after=_of(["a", "b"]))
    goes: RecordChange = diff_records(before=_of(["a", "b"]), after={"tables": {}})

    assert appears["fields"]["order"] == [None, ["a", "b"]]
    assert goes["fields"]["order"] == [["a", "b"], None]
    assert apply_change(record={"tables": {}}, change=appears, forward=True)["order"] == ["a", "b"]
    assert "order" not in apply_change(record=_of(["a", "b"]), change=appears, forward=False)


@pytest.mark.unit
def test_a_change_that_does_not_fit_the_record_is_refused_not_applied_wrongly() -> None:
    change: RecordChange = _change(before=["a", "b", "c"], after=["a", "c"])

    with pytest.raises(ValueError, match="takes out ids"):
        apply_change(record=_of(["a", "c"]), change=change, forward=True)

    with pytest.raises(ValueError, match="no place"):
        apply_change(record=_of([]), change=change, forward=False)

    with pytest.raises(ValueError, match="record has none"):
        apply_change(record={"tables": {}}, change=change, forward=True)


@pytest.mark.unit
@pytest.mark.parametrize("seed", range(15))
def test_a_whole_record_with_rows_and_lists_round_trips_through_many_edits(seed: int) -> None:
    rng: random.Random = random.Random(seed)
    record: DocumentRecord = {
        "music_revision": "r0",
        "measure_ids": _ids(30),
        "relation_ids": _ids(200),
        "tables": {"notes": {f"n{number}": {"step": number} for number in range(100)}},
    }
    states: list[DocumentRecord] = [record]
    for step in range(25):
        nxt: DocumentRecord = {
            **states[-1],
            "music_revision": f"r{step + 1}",
            "measure_ids": list(states[-1]["measure_ids"]),
            "relation_ids": list(states[-1]["relation_ids"]),
            "tables": {"notes": dict(states[-1]["tables"]["notes"])},
        }
        for name in ("measure_ids", "relation_ids"):
            items: list[str] = nxt[name]
            for _ in range(rng.randint(0, 4)):
                if items and rng.random() < 0.5:
                    del items[rng.randrange(len(items))]
                else:
                    items.insert(rng.randint(0, len(items)), f"{name}{rng.randint(0, 10**6)}")

        for _ in range(rng.randint(0, 3)):
            row: str = f"n{rng.randint(0, 120)}"
            if row in nxt["tables"]["notes"] and rng.random() < 0.5:
                del nxt["tables"]["notes"][row]
            else:
                nxt["tables"]["notes"][row] = {"step": rng.randint(0, 50)}

        states.append(nxt)

    changes: list[RecordChange] = [
        json.loads(json.dumps(diff_records(before=states[i], after=states[i + 1]), sort_keys=True))
        for i in range(len(states) - 1)
    ]

    walked: DocumentRecord = states[0]
    for index, change in enumerate(changes):
        walked = apply_change(record=walked, change=change, forward=True)
        assert walked == states[index + 1]

    for index in reversed(range(len(changes))):
        walked = apply_change(record=walked, change=changes[index], forward=False)
        assert walked == states[index]
