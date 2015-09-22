from django.shortcuts import render
from django.views.generic import View


class SampleMapPicker(View):
    template_name = 'samples/picker_map.html'

    def get(self, request, *args, **kwargs):
        return render(request,
                      self.template_name,
                      {})
