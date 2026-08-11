import datetime
from dataclasses import dataclass
from http import HTTPStatus
from queue import SimpleQueue

import requests

from minibrain.context import Context
from minibrain.utils.network import declares_ip6, get_domain_for

USER_AGENT = "Minibrain Probe (see https://lb.download.kiwix.org/probe_info)"

context = Context.get()
logger = context.logger


@dataclass
class ProbeResponse:
    on: datetime.datetime
    mirror: str
    url: str
    ip4_status_code: HTTPStatus | None = None
    ip4_error: str = ""
    ip6_requested: bool = False
    ip6_declared: bool = False
    ip6_status_code: HTTPStatus | None = None
    ip6_error: str = ""

    @property
    def status_code(self) -> HTTPStatus | None:
        values: list[HTTPStatus] = []
        if self.ip4_status_code:
            values.append(self.ip4_status_code)
        if self.ip6_status_code:
            values.append(self.ip6_status_code)
        return max(values) if values else None

    @property
    def error(self) -> str:
        return (
            f"IPv4: {self.ip4_error}, IPv6: {self.ip6_error}"
            if self.ip6_error
            else self.ip4_error
        )

    @property
    def ip4_succeeded(self) -> bool:
        return self.ip4_status_code == HTTPStatus.OK

    @property
    def ip4_response(self) -> str:
        if self.ip4_status_code:
            return f"{self.ip4_status_code!s}: {self.ip4_status_code.name}"
        return self.ip4_error

    @property
    def ip6_succeeded(self) -> bool:
        return self.ip6_status_code == HTTPStatus.OK

    @property
    def ip6_response(self) -> str:
        if not self.ip6_requested and self.ip6_declared:
            return "offered but not requested"
        elif not self.ip6_requested:
            return "neither requested nor offered."
        if not self.ip6_declared:
            return "not offered"

        if self.ip6_status_code:
            return f"{self.ip6_status_code!s}: {self.ip6_status_code.name}"
        return self.ip6_error

    @property
    def succeeded(self) -> bool:
        return (
            self.ip4_succeeded and self.ip6_succeeded
            if self.ip6_requested and self.ip6_declared
            else self.ip4_succeeded
        )

    @property
    def response(self) -> str:
        return f"IPv4: {self.ip4_response}, IPv6: {self.ip6_response}"

    def __str__(self) -> str:
        return f"{self.mirror} ({self.url}): {self.response}"


def probe_mirror(
    *, mirror: str, base_url: str, v4_only: bool, timeout: int = 5
) -> ProbeResponse:
    now = datetime.datetime.now(tz=datetime.UTC)

    ip4_status_code: HTTPStatus | None = None
    ip6_status_code: HTTPStatus | None = None
    ip6_requested: bool = not v4_only
    ip6_declared: bool = False

    all_urls: SimpleQueue[str] = SimpleQueue()
    all_urls.put(base_url)
    checked_urls: set[str] = set()

    # looping over a list of URLs (starting with base_url)
    # as we want to check that whether any intermediate redirect
    # declares IPv6
    while not all_urls.empty():
        url = all_urls.get()
        if url in checked_urls:
            continue

        try:
            ip6_declared = declares_ip6(get_domain_for(url))
        except Exception:
            logger.debug(f"Exception querying AAAA for {url}")
            ip6_declared = False

        try:
            # test IPv4 first and anyway
            logger.debug(f"[v4] {url}")
            ip4_resp = requests.get(
                url=url,
                headers={"Accept": "*/*", "User-Agent": USER_AGENT},
                stream=True,
                allow_redirects=True,
                timeout=timeout,
            )

            if ip4_resp.is_redirect and ip4_resp.next and ip4_resp.next.url:
                all_urls.put(ip4_resp.next.url)

            ip4_status_code = HTTPStatus(ip4_resp.status_code)

        except Exception as exc:
            return ProbeResponse(
                on=now,
                mirror=mirror,
                url=base_url,
                ip4_error=str(exc),
                ip6_declared=ip6_declared,
                ip6_requested=ip6_requested,
            )

        if ip6_requested and ip6_declared:
            logger.debug(f"[v6] {url}")

            try:
                ip6_resp = requests.get(
                    url=url,
                    headers={"Accept": "*/*", "User-Agent": USER_AGENT},
                    stream=True,
                    allow_redirects=True,
                    timeout=timeout,
                    proxies=context.ip6_proxies,
                )
                if ip6_resp.is_redirect and ip6_resp.next and ip6_resp.next.url:
                    all_urls.put(ip6_resp.next.url)

                ip6_status_code = HTTPStatus(ip6_resp.status_code)

            except OSError as exc:
                raise exc
            except Exception as exc:
                return ProbeResponse(
                    on=now,
                    mirror=mirror,
                    url=base_url,
                    ip4_status_code=ip4_status_code,
                    ip6_error=str(exc),
                    ip6_requested=ip6_requested,
                    ip6_declared=ip6_declared,
                )

            checked_urls.add(url)

    return ProbeResponse(
        on=now,
        mirror=mirror,
        url=base_url,
        ip4_status_code=ip4_status_code,
        ip6_requested=ip6_requested,
        ip6_declared=ip6_declared,
        ip6_status_code=ip6_status_code,
    )
