from http import HTTPStatus

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from peewee import DoesNotExist

from minibrain.context import Context
from minibrain.utils.fileinfo import FileInfo, get_fileinfo
from minibrain.utils.status import Status, get_status
from minibrain.utils.wellknown import get_most_mirrored

context = Context.get()
logger = context.logger


app = FastAPI()


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/status.json")
def status() -> Status:
    return get_status()


@app.get("/{path:path}.lb")
def entry(path: str) -> FileInfo:
    if not path.startswith("zim/") or not path.endswith(".zim"):
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST)
    try:
        return get_fileinfo(path=path)
    except DoesNotExist as exc:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from exc


@app.get("/well-known/most-mirrored.json")
def most_mirrored_zims() -> list[FileInfo]:
    return get_most_mirrored(nb_results=2)
