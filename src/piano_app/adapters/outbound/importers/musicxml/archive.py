import zipfile
from io import BytesIO
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeElementTree

from piano_app.application.ports.importing import ImportRefusedError

MAX_XML_BYTES: int = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES: int = 200
MAX_COMPRESSION_RATIO: int = 200

ZIP_MAGIC: bytes = b"PK\x03\x04"

_CONTAINER_PATH: str = "META-INF/container.xml"


def xml_bytes_of(*, data: bytes) -> bytes:
    """The MusicXML document in a file: the file itself, or the main file of a compressed
    (``.mxl``) archive. The size is checked while it is read, not by what the archive claims."""
    if not data.startswith(ZIP_MAGIC):
        if len(data) > MAX_XML_BYTES:
            raise ImportRefusedError(reason="The file is too large.")

        return data

    try:
        archive: zipfile.ZipFile = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ImportRefusedError(reason="The archive cannot be opened.") from error

    with archive:
        if len(archive.infolist()) > MAX_ARCHIVE_ENTRIES:
            raise ImportRefusedError(reason="The archive holds too many files.")

        container: bytes = _read_member(archive=archive, name=_CONTAINER_PATH)
        main_path: str = _main_file_path(container=container)

        return _read_member(archive=archive, name=main_path)


def _read_member(*, archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        info: zipfile.ZipInfo = archive.getinfo(name)
    except KeyError as error:
        raise ImportRefusedError(reason=f"The archive has no {name}.") from error

    if info.file_size > MAX_XML_BYTES:
        raise ImportRefusedError(reason="The file inside the archive is too large.")

    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise ImportRefusedError(reason="The archive is not a plausible score.")

    with archive.open(info) as member:
        content: bytes = member.read(MAX_XML_BYTES + 1)

    if len(content) > MAX_XML_BYTES:
        raise ImportRefusedError(reason="The file inside the archive is too large.")

    return content


def _main_file_path(*, container: bytes) -> str:
    try:
        root: Element = SafeElementTree.fromstring(container)
    except (ParseError, DefusedXmlException) as error:
        raise ImportRefusedError(reason="The archive's container.xml cannot be read.") from error

    for rootfile in root.iter("rootfile"):
        path: str | None = rootfile.get("full-path")
        if path:
            return path

    raise ImportRefusedError(reason="The archive names no main file.")
