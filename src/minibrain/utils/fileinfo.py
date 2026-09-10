import datetime
from pathlib import Path

from peewee import DoesNotExist
from pydantic import BaseModel

from minibrain.context import Context
from minibrain.db import Filearr, Hash, Server
from minibrain.utils.db import get_geo_summary, get_mirrors_summaries

context = Context.get()
logger = context.logger


class MirrorEntry(BaseModel):
    ident: str
    serving: str
    enabled: bool
    online: bool
    url: str


class FileInfo(BaseModel):
    fileid: int
    path: str
    filename: str
    folder: str
    mtime: datetime.datetime
    size: int
    md5: str | None = None
    sha1: str | None = None
    sha1_piecesize: int | None = None
    sha256: str | None = None
    btih: str | None = None
    mirrors: list[MirrorEntry]


def get_fileinfo(*, path: str) -> FileInfo:

    all_mirrors = get_mirrors_summaries()
    try:
        file = Filearr.get(Filearr.path == path)
        hashes = Hash.get(Hash.file == file)
    except DoesNotExist:
        logger.error(f"No file found with {path=}")
        raise

    fpath = Path(file.path)

    mirrors: list[MirrorEntry] = []
    for mirror_id in file.mirrors:
        mirror = all_mirrors[mirror_id]
        mirrors.append(
            MirrorEntry(
                ident=mirror.ident,
                serving=get_geo_summary(Server.get(mirror_id)),
                url=f"{mirror.baseurl}{path}",
                enabled=mirror.enabled,
                online=mirror.status,
            )
        )

    return FileInfo(
        fileid=file.id,
        path=str(fpath),
        filename=fpath.name,
        folder=str(fpath.parent),
        mtime=hashes.mtime,
        size=hashes.size,
        md5=hashes.md5.hex() if hashes.md5 else None,
        sha1=hashes.sha1.hex() if hashes.sha1 else None,
        sha1_piecesize=hashes.sha1piecesize or None,
        sha256=hashes.sha256.hex() if hashes.sha256 else None,
        btih=hashes.btih.hex() if hashes.btih else None,
        mirrors=mirrors,
        nb_mirrors=len(mirrors),
    )
