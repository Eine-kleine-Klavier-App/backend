class ImportRefusedError(Exception):
    """The file cannot be imported at all: no draft is made.

    ``reason`` is a message the user can read as it is (not a MusicXML file, too large, more
    than one part, ...).
    """

    def __init__(self, *, reason: str) -> None:
        super().__init__(reason)
        self.reason: str = reason
