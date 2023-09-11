class TenantDataclassException(Exception):
    pass


class TenantNotFoundException(Exception):
    def __init__(self, *args: object, domain: str = "") -> None:
        super().__init__(*args)
        self.domain = domain

    def __str__(self):
        return "Tenant for host: '{domain}' not found".format(domain=self.domain)


class TenantNotFoundInLocalThreadException(Exception):
    def __str__(self):
        return "Tenant not found in local thread"
