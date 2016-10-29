import rest_framework.serializers as serializers


class ChoiceField(serializers.ChoiceField):
    @property
    def object_choices(self):
        if not self.grouped_choices:
            return {}
        return self.grouped_choices
