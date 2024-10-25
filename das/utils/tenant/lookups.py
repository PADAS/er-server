import logging
import re
from dataclasses import dataclass
from typing import Pattern

from utils.tenant.exceptions import WrongTenantIdentifier

logger = logging.getLogger(__name__)


@dataclass
class TenantLookupRegexPatterns:
    uuid_pattern: Pattern[str] = re.compile(r"\w{8}-\w{4}-\w{4}-\w{4}-\w{12}")
    domain_pattern: Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9](?:\.[a-zA-Z]{2,})+$")
    slug_name_pattern: Pattern[str] = re.compile(r"^(?![0-9-]+$)(?:[a-z]{2,}-?|[0-9]-?)+(?<!-)$")


def get_tenant_lookup_type(lookup: str) -> str:
    if re.fullmatch(TenantLookupRegexPatterns.uuid_pattern, lookup):
        identifier_type = "id"
    elif re.fullmatch(TenantLookupRegexPatterns.domain_pattern, lookup):
        identifier_type = "domain"
    elif re.fullmatch(TenantLookupRegexPatterns.slug_name_pattern, lookup):
        identifier_type = "slugName"
    else:
        raise WrongTenantIdentifier
    logger.info("tenant_identifier: %s is type: %s", lookup, identifier_type)
    return identifier_type
