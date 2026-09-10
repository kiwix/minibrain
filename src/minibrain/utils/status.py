# pyright: strict, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import datetime

from peewee import PostgresqlDatabase
from pydantic import BaseModel

from minibrain.context import Context
from minibrain.db import Server, database
from minibrain.utils.db import get_geo_summary

context = Context.get()
logger = context.logger


def get_single_int(db: PostgresqlDatabase, query: str, args: tuple[str | int]) -> int:
    return get_single(db, query, args)  # pyright:  ignore


def get_single(
    db: PostgresqlDatabase, query: str, args: tuple[str | int]
) -> str | int | bytes | list[int]:
    return next(db.execute_sql(query, args))[0]  # pyright: ignore


class MirrorConfig(BaseModel):
    prefix_only: bool
    prefix: str
    as_only: bool
    asn: int
    region_only: bool
    region: str
    country_only: bool
    country: str
    other_countries: list[str]


class MirrorStatus(BaseModel):
    dbid: int
    ident: str
    enabled: bool
    online: bool
    last_scan_on: datetime.datetime | None
    nb_files: int
    total_size: int
    score: int
    serving: str
    conf: MirrorConfig


class Status(BaseModel):
    on: datetime.datetime
    mirrors: list[MirrorStatus]


def get_status() -> Status:

    Context.get()

    now = datetime.datetime.now(tz=datetime.UTC)

    mirrors: list[MirrorStatus] = []

    for server in Server.select().order_by(
        Server.enabled.desc(), Server.identifier.asc()
    ):
        nb_files: int = get_single_int(
            database, "SELECT mirr_get_nfiles(%s);", (server.id,)
        )

        total_size: int = (
            get_single_int(
                database,
                "SELECT SUM(hash.size) as total FROM hash "
                "INNER JOIN filearr ON filearr.id = hash.file_id "
                "WHERE %s = ANY(filearr.mirrors);",
                (server.id,),
            )
            or 0
        )

        mirrors.append(
            MirrorStatus(
                dbid=server.id,
                ident=server.identifier,
                enabled=server.enabled,
                online=server.status_baseurl,
                last_scan_on=server.last_scan or None,
                nb_files=nb_files,
                total_size=total_size,
                score=server.score,
                serving=get_geo_summary(server),
                conf=MirrorConfig(
                    prefix_only=server.prefix_only,
                    prefix=server.prefix,
                    as_only=server.as_only,
                    asn=server.asn,
                    region_only=server.region_only,
                    region=server.region,
                    country_only=server.country_only,
                    country=server.country,
                    other_countries=server.other_countries.split(","),
                ),
            )
        )

    return Status(on=now, mirrors=mirrors)
