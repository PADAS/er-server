import logging

from django.contrib.admin import AdminSite
from django.utils.translation import ugettext_lazy as _

from observations.models import Subject, SubjectSource, Source, Observation
from observations.admin import SubjectAdmin, SubjectSourceAdmin, SourceAdmin

logger = logging.getLogger(__name__)


class DasAdminSite(AdminSite):

    site_header = _('DAS Administration')
    site_title = _('DAS Administration')
    index_title = _('DAS Administratiion : Observations')

    def get_app_list(self, request):
        applist = super(DasAdminSite, self).get_app_list(request)
        return applist


dasadmin_site = DasAdminSite(name='das_admin')

for x in (Subject, SubjectAdmin), (SubjectSource, SubjectSourceAdmin), (Source, SourceAdmin), (Observation, None):
    dasadmin_site.register(*x)
