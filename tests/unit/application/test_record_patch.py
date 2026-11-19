import pytest

from piano_app.application.ports.score import DocumentRecord
from piano_app.application.use_cases.score.shared.record_patch import (
    apply_change,
    diff_records,
    inverted,
)


def _record() -> DocumentRecord:
    return {
        "music_revision": "r1",
        "measure_ids": ["m1", "m2"],
        "tables": {
            "measures": {"m1": {"count": 4}, "m2": {"count": 4}},
            "notes": {"n1": {"step": 3}, "n2": {"step": 5}},
        },
    }


@pytest.mark.unit
def test_equal_records_have_no_change() -> None:
    assert diff_records(before=_record(), after=_record()) == {}


@pytest.mark.unit
def test_a_changed_row_is_the_whole_change() -> None:
    after: DocumentRecord = _record()
    after["tables"]["notes"]["n1"] = {"step": 4}

    assert diff_records(before=_record(), after=after) == {
        "tables": {"notes": {"n1": [{"step": 3}, {"step": 4}]}}
    }


@pytest.mark.unit
def test_an_added_and_a_removed_row_have_none_on_the_side_they_lack() -> None:
    after: DocumentRecord = _record()
    del after["tables"]["notes"]["n2"]
    after["tables"]["notes"]["n3"] = {"step": 7}

    assert diff_records(before=_record(), after=after) == {
        "tables": {"notes": {"n2": [{"step": 5}, None], "n3": [None, {"step": 7}]}}
    }


@pytest.mark.unit
def test_a_plain_field_is_changed_whole_and_a_list_of_ids_by_what_left_and_came_in() -> None:
    after: DocumentRecord = _record()
    after["music_revision"] = "r2"
    after["measure_ids"] = ["m1", "m3", "m2"]

    assert diff_records(before=_record(), after=after) == {
        "fields": {
            "measure_ids": {"removed": [], "inserted": [[1, "m3"]]},
            "music_revision": ["r1", "r2"],
        }
    }


@pytest.mark.unit
def test_a_table_that_appears_or_goes_is_its_rows() -> None:
    after: DocumentRecord = _record()
    after["tables"]["marks"] = {"k1": {"kind": "accent"}}
    del after["tables"]["measures"]

    assert diff_records(before=_record(), after=after) == {
        "tables": {
            "marks": {"k1": [None, {"kind": "accent"}]},
            "measures": {"m1": [{"count": 4}, None], "m2": [{"count": 4}, None]},
        }
    }


@pytest.mark.unit
def test_a_change_applies_forward_and_takes_back() -> None:
    before: DocumentRecord = _record()
    after: DocumentRecord = _record()
    after["tables"]["notes"]["n1"] = {"step": 4}
    del after["tables"]["notes"]["n2"]
    after["tables"]["notes"]["n3"] = {"step": 7}
    after["music_revision"] = "r2"
    change = diff_records(before=before, after=after)

    assert apply_change(record=before, change=change, forward=True) == after
    assert apply_change(record=after, change=change, forward=False) == before


@pytest.mark.unit
def test_applying_a_change_leaves_the_record_it_was_given_as_it_was() -> None:
    before: DocumentRecord = _record()
    after: DocumentRecord = _record()
    after["tables"]["notes"]["n1"] = {"step": 4}
    after["music_revision"] = "r2"

    apply_change(record=before, change=diff_records(before=before, after=after), forward=True)

    assert before == _record()


@pytest.mark.unit
def test_rows_a_change_does_not_touch_are_shared_with_the_new_record() -> None:
    before: DocumentRecord = _record()
    after: DocumentRecord = _record()
    after["tables"]["notes"]["n1"] = {"step": 4}

    applied: DocumentRecord = apply_change(
        record=before, change=diff_records(before=before, after=after), forward=True
    )

    assert applied["tables"]["notes"]["n2"] is before["tables"]["notes"]["n2"]
    assert applied["tables"]["measures"] is before["tables"]["measures"]


@pytest.mark.unit
def test_taking_back_a_field_the_record_did_not_have_removes_it() -> None:
    before: DocumentRecord = _record()
    after: DocumentRecord = _record()
    after["pedal"] = "down"
    change = diff_records(before=before, after=after)

    taken_back: DocumentRecord = apply_change(record=after, change=change, forward=False)

    assert taken_back == before
    assert "pedal" not in taken_back


@pytest.mark.unit
def test_a_table_the_record_did_not_have_is_not_made_by_a_change_that_puts_nothing_in_it() -> None:
    change = {"tables": {"marks": {"k1": [{"kind": "accent"}, None]}}}

    applied: DocumentRecord = apply_change(record=_record(), change=change, forward=True)

    assert "marks" not in applied["tables"]


@pytest.mark.unit
def test_the_inverted_change_takes_a_change_back() -> None:
    before: DocumentRecord = _record()
    after: DocumentRecord = {
        "music_revision": "r2",
        "measure_ids": ["m2", "m3"],
        "tables": {
            "measures": {"m2": {"count": 3}, "m3": {"count": 4}},
            "notes": {"n1": {"step": 4}, "n3": {"step": 0}},
        },
    }
    change = diff_records(before=before, after=after)

    assert apply_change(record=after, change=inverted(change=change), forward=True) == before
    assert inverted(change=inverted(change=change)) == change
    assert inverted(change={}) == {}
