from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

# What a note carries in <notations>, by the MusicXML names the source score keeps.

_ARTICULATIONS: frozenset[str] = frozenset(
    {"staccato", "staccatissimo", "tenuto", "accent", "strong-accent"}
)
_ORNAMENTS: frozenset[str] = frozenset(
    {"trill-mark", "mordent", "inverted-mordent", "turn", "inverted-turn"}
)
# Said about the notation, not about the music: the ties come from <tie>, the tuplets from
# <time-modification>.
_NOT_REPORTED: frozenset[str] = frozenset({"tied", "tuplet", "accidental-mark"})
_FINGERS: frozenset[str] = frozenset({"1", "2", "3", "4", "5"})


@dataclass(kw_only=True)
class NoteMarks:
    articulations: set[str] = field(default_factory=set)
    ornament: str | None = None
    fingering: int | None = None
    slurs: list[tuple[str, int]] = field(default_factory=list)
    """``(type, number)`` of each slur sign on the note."""

    skipped: list[str] = field(default_factory=list)
    """What the note carries that the score has no place for."""


def read_marks(*, notations: list[Element]) -> NoteMarks:
    marks: NoteMarks = NoteMarks()
    for element in notations:
        for child in element:
            _read_child(child=child, marks=marks)

    return marks


def _read_child(*, child: Element, marks: NoteMarks) -> None:
    tag: str = child.tag
    if tag == "slur":
        kind: str | None = child.get("type")
        if kind in ("start", "stop"):
            marks.slurs.append((kind, int(child.get("number") or "1")))
    elif tag == "fermata":
        marks.articulations.add("fermata")
    elif tag == "arpeggiate":
        marks.articulations.add(
            "arpeggio-down" if child.get("direction") == "down" else "arpeggio-up"
        )
    elif tag == "articulations":
        for item in child:
            if item.tag in _ARTICULATIONS:
                marks.articulations.add(item.tag)
            else:
                marks.skipped.append(item.tag)
    elif tag == "ornaments":
        for item in child:
            _read_ornament(item=item, marks=marks)
    elif tag == "technical":
        for item in child:
            text: str = (item.text or "").strip()
            if item.tag == "fingering" and text in _FINGERS:
                marks.fingering = int(text)
            else:
                marks.skipped.append(item.tag)
    elif tag not in _NOT_REPORTED:
        marks.skipped.append(tag)


def _read_ornament(*, item: Element, marks: NoteMarks) -> None:
    if item.tag in _ORNAMENTS:
        marks.ornament = item.tag
    elif item.tag == "tremolo" and item.get("type", "single") == "single":
        marks.ornament = f"tremolo-{(item.text or '').strip() or '1'}"
    elif item.tag not in _NOT_REPORTED:
        marks.skipped.append(item.tag)
