# pyright: strict, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from dataclasses import dataclass

from minibrain.db import Server, Version, database

AREAS = {
    "Americas": "ag,ai,ar,aw,bb,bl,bm,bo,bq,br,bs,bz,ca,cl,co,cr,cu,cw,dm,do,ec,fk,"
    "gd,gf,gl,gp,gt,gy,hn,ht,jm,kn,ky,lc,mf,mq,ms,mx,ni,pa,pe,pm,pr,py,sr,sv,sx,tc,"
    "tt,us,uy,vc,ve,vg,vi"
}


def get_mb_version() -> str:
    version: Version = Version.get(id=1)
    return f"{version.major!s}.{version.minor!s}.{version.patchlevel!s}"


@dataclass
class MirrorSummary:
    ident: str
    baseurl: str
    status: bool
    enabled: bool


def get_mirrors_summaries() -> dict[int, MirrorSummary]:
    from minibrain.db import Server  # noqa: PLC0415

    return {
        server.id: MirrorSummary(
            ident=server.identifier,
            baseurl=server.baseurl,
            status=server.status_baseurl,
            enabled=server.enabled,
        )
        for server in Server.select()
    }


class Temp:
    _regions: dict[str, str]
    _countries: dict[str, str]

    @classmethod
    def query(cls):
        cls._regions = {}
        for code, name in database.execute_sql("SELECT code, name FROM region;"):
            cls._regions[code] = name

        cls._countries = {}
        for code, name in database.execute_sql("SELECT code, name FROM country;"):
            cls._countries[code] = name

    @classmethod
    def regions(cls) -> dict[str, str]:
        if not getattr(cls, "_regions", {}):
            cls.query()
        return getattr(cls, "_regions", {})

    @classmethod
    def countries(cls) -> dict[str, str]:
        if not getattr(cls, "_countries", {}):
            cls.query()
        return getattr(cls, "_countries", {})


def get_geo_summary(server: Server) -> str:
    regions = Temp.regions()
    countries = Temp.countries()

    text = ""
    worldwide = False
    if server.prefix_only:
        text = f"Only {server.prefix}"
    elif server.as_only:
        text = f"Only AS {server.asn}"
    elif server.region_only:
        text = f"{regions.get(str(server.region), server.region)}"
    elif server.country_only and server.country != "**":
        text = f"Only {countries.get(str(server.country), server.country)}"
    else:
        worldwide = True

    if server.other_countries:
        zone = ", ".join(
            [
                str(countries.get(oc, oc))
                for oc in str(server.other_countries).split(",")
            ]
        )
        for name, other_countries in AREAS.items():
            if server.other_countries == other_countries:
                zone = name
                break
        if text:
            text += " plus "
        text += zone

    if worldwide:
        text = "Worldwide"

    return text
