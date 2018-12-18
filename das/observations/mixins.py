class FilterMixin(object):

    def by_id(self, primary_keys):
        if isinstance(primary_keys, str):
            primary_keys = [primary_key.strip() for primary_key in 
            primary_keys.split(',') if primary_key]
        return self.filter(id__in=primary_keys)
