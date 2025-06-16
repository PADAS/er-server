class PartialUpdateMixin:
    allowed_partial_update_fields = []  # Default value, expected to be overridden in child class
    partial_update_side_effects = []  # Default value, expected to be overridden in child class

    def update(self, instance, validated_data):
        update_fields = []
        for k, v in validated_data.items():
            if k not in self.allowed_partial_update_fields:
                continue
            if getattr(instance, k) != v:
                setattr(instance, k, v)
                update_fields.append(k)
        if update_fields:
            update_fields.extend(self.partial_update_side_effects)
            instance.save(update_fields=update_fields)
        return instance
