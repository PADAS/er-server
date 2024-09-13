class PartialUpdateMixin:
    allowed_partial_update_fields = []  # Default value, expected to be overridden in child class

    def update(self, instance, validated_data):
        update_fields = []
        for k, v in validated_data.items():
            if k not in self.allowed_partial_update_fields:
                continue
            if getattr(instance, k) != v:
                setattr(instance, k, v)
                update_fields.append(k)
        if update_fields:
            instance.save(update_fields=update_fields)
        return instance
