from minibrain.context import Context
from minibrain.db import database
from minibrain.utils.fileinfo import FileInfo, get_fileinfo

context = Context.get()
logger = context.logger


def get_most_mirrored(nb_results: int) -> list[FileInfo]:
    """most (nb_results) mirrored ZIMs"""
    return [
        get_fileinfo(path=row[0])  # type: ignore
        for row in database.execute_sql(  # type: ignore
            "SELECT path FROM filearr WHERE mirrors is not null "
            "ORDER BY cardinality(mirrors) DESC LIMIT %s;",
            (nb_results,),
        )
    ]
