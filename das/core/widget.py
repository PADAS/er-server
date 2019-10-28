import os
from django.forms.widgets import Widget
from django.contrib.staticfiles.storage import staticfiles_storage


class IconKeyInput(Widget):
    input_type = 'text'
    template_name = 'admin/core/icon_key_widget.html'

    def __init__(self, attrs=None, image_list_fn=None):
        if attrs is not None:
            attrs = attrs.copy()
            self.input_type = attrs.pop('type', self.input_type)
        self.image_list_fn = image_list_fn
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['type'] = self.input_type
        image_list = list(self.image_list_fn())
        context['image_list'] = image_list

        if context['widget']['value']:
            try:
                context['widget']['file_path'] = \
                    next(o for o in image_list if o['key'] == context['widget']['value'])[
                    'file_path']
            except StopIteration:
                pass

        return context

    class Media:
        css = {
            'all': ('css/icon_key_text.css', ),
        }


def get_icon_select_list(dirname='sprite-src'):
    icon_list = [
        {
            'key': item.split('.')[0],
            'file_path': staticfiles_storage.url(os.sep.join((dirname, item)))
        }
        for item in staticfiles_storage.listdir(dirname)[1]
    ]
    return sorted(icon_list, key=lambda icon: icon['key'])