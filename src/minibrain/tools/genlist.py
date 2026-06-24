# pyright: strict, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import json
import sys
from pathlib import Path

from peewee import PostgresqlDatabase
from rich.status import Status

from minibrain.context import Context
from minibrain.db import Server, database
from minibrain.utils.db import get_geo_summary, get_mb_version

context = Context.get()
logger = context.logger


def get_single_int(db: PostgresqlDatabase, query: str, args: tuple[str | int]) -> int:
    return get_single(db, query, args)  # pyright:  ignore


def get_single(
    db: PostgresqlDatabase, query: str, args: tuple[str | int]
) -> str | int | bytes | list[int]:
    return next(db.execute_sql(query, args))[0]  # pyright: ignore


def gen_json_mirrorlist(to_path: Path | None) -> int:

    logger.info(f"Starting status for {context.dsn}")
    logger.warning(f"Connected to mirrorbrain DB version {get_mb_version()}")

    metadata = {}
    mirrors = []

    with Status("Querying database…", console=context.console):
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
            serving_str = get_geo_summary(server)

            mirrors.append(
                {
                    "identifier": server.identifier,
                    "http_url": server.baseurl,
                    "ftp_url": server.baseurl_ftp,
                    "rsync_url": server.baseurl_rsync,
                    "enabled": server.enabled,
                    "region": server.region,
                    "country": server.country,
                    "asn": server.asn,
                    "prefix": server.prefix,
                    "ipv6_only": server.ipv6_only,
                    "score": server.score,
                    "operator_url": server.operator_url,
                    "public_notes": server.public_notes,
                    "lat": float(server.lat),
                    "lon": float(server.lng),
                    "country_only": server.country_only,
                    "region_only": server.region_only,
                    "as_only": server.as_only,
                    "prefix_only": server.prefix_only,
                    "other_countries": server.other_countries,
                    "file_maxsize": server.file_maxsize,
                    "serving": serving_str,
                    "nb_files": nb_files,
                    "total_size": int(total_size),
                }
            )
        metadata["mirrors"] = mirrors

    if to_path:
        to_path.write_text(json.dumps(metadata, indent=4))
    else:
        print(json.dumps(metadata, indent=4), file=sys.stdout)  # noqa: T201

    return 0
