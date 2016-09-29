import datetime, pytz
from django.shortcuts import render
from django.views.generic import TemplateView
from django.template.response import TemplateResponse

# from jinja2 import Environment
# from django.contrib.staticfiles.storage import staticfiles_storage
# from django.core.urlresolvers import reverse
#
# def environment(**options):
#     env = Environment(**options)
#     env.globals.update({
#        'static': staticfiles_storage.url,
#        'url': reverse,
#     })
#     return env

class SitRepReport(TemplateView):

    def render_to_response(self, context, **response_kwargs):


        response = super().render_to_response(context, **response_kwargs)
        response['Content-Disposition'] = 'attachement; filename={}'.format(context['report_filename'])
        return response

    # response_class = SomeResponseClass
    response_class = TemplateResponse
    content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    template_engine = 'docx_template'
    template_name = 'lewa_sitrep_template.docx'

    def get_context_data(self, **kwargs):
        report_date = pytz.utc.localize(datetime.datetime.utcnow())
        context = {
            'report_filename': 'sitrep_report-{}.docx'.format(report_date.strftime('%Y-%m-%d')),
            'report_date': report_date.astimezone(pytz.timezone('Africa/Nairobi')).strftime(
                '%d-%b-%y %Z'),
            'rhino_sightings': [
                {'type': 'Black Rhino',
                 'count': 53
                 },
                {'type': 'White Rhino', 'count': 61}
            ]
        }
        return context


