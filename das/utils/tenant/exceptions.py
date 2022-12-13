class TenantDataclassException(Exception):
    pass


class TenantNotFoundException(Exception):
    def __init__(self, host: str = "", *args: object) -> None:
        super().__init__(*args)
        self.host = host

    def __str__(self):
        return "Tenant for host: '{host}' not found".format(host=self.host)
