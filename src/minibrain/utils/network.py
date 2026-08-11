# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportOptionalMemberAccess=false
from urllib.parse import urlsplit

import dns.rdatatype
import dns.resolver

from minibrain.context import Context

context = Context.get()
logger = context.logger


def declares_ip6(domain: str) -> bool:
    """whether a domain name has an AAAA record"""
    try:
        result = dns.resolver.resolve(domain, "AAAA")
        for record in result.response.answer:
            if record.rdtype == dns.rdatatype.AAAA:
                return True
            if (
                record.rdtype == dns.rdatatype.CNAME
                and result.rrset.name.to_text() not in (domain, f"{domain}.")
            ):
                return declares_ip6(result.rrset.name.to_text())  # pyright: ignore[reportUnknownArgumentType]
            return result.rrset.rdtype == dns.rdatatype.AAAA
    except dns.resolver.NoAnswer:
        return False
    except Exception as exc:
        logger.error(f"Exception querying AAAA for {domain}: {exc}")
        logger.exception(exc)
        return False
    return False


def get_domain_for(url: str) -> str:
    """domain name from URL so we can query DNS"""
    return urlsplit(url).hostname or ""
