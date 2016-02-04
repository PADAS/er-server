from django.shortcuts import render
from django.views.generic import View


class RTMClient(View):
    template_name = 'rtmclient.html'

    def get(self, request, *args, **kwargs):
        return render(request,
                      self.template_name,
                      {})
