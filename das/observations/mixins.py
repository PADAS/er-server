import uuid

class FilterMixin(object):

    def by_id(self, primary_keys):
        if isinstance(primary_keys, str):
            primary_keys = [uuid.UUID(pk.strip()) for pk in primary_keys.split(',')]
        return self.filter(id__in=primary_keys)
