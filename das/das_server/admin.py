import logging

from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _

from observations.admin import (SourceAdmin, SubjectAdmin, SubjectGroupAdmin,
                                SubjectSourceAdmin, SubjectSourceSummaryAdmin,
                                SubjectStatusAdmin, SubjectSubTypeAdmin,
                                SubjectTypeAdmin)
from observations.models import (Source, Subject, SubjectGroup, SubjectSource,
                                 SubjectSourceSummary, SubjectStatus,
                                 SubjectSubType, SubjectType)

logger = logging.getLogger(__name__)


class DasAdminSite(AdminSite):
    site_title = _("EarthRanger Administration (simple view)")
    site_header = site_title
    index_title = site_title
    enable_nav_sidebar = False

    index_template = "admin/simple_admin_index.html"

    def get_app_list(self, request):
        applist = super().get_app_list(request)
        return applist


dasadmin_site = DasAdminSite(name="das_admin")

for x in (
    (Subject, SubjectAdmin),
    (SubjectSource, SubjectSourceAdmin),
    (Source, SourceAdmin),
    (SubjectStatus, SubjectStatusAdmin),
    (SubjectType, SubjectTypeAdmin),
    (SubjectSubType, SubjectSubTypeAdmin),
    (SubjectGroup, SubjectGroupAdmin),
    (SubjectSourceSummary, SubjectSourceSummaryAdmin),
):
    dasadmin_site.register(*x)
