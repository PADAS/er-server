
class ContextMixin(object):
    def get_serializer_context(self):
        context = {}
        context['request'] = self.request
        return context