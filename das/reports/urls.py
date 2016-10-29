"""api URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf.urls import url, include
from rest_framework.urlpatterns import format_suffix_patterns
from reports import views


urlpatterns = [
    url(r'^sitrep\.docx$', views.SituationReportView.as_view(
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        template_engine = 'docx_template',
        template_name = 'lewa_sitrep_template.docx')),
    url(r'^sitrep\.html$', views.SituationReportView.as_view(
        content_type='text/html',
        template_engine='jinja2',
        template_name='lewa_sitrep_template.html')),
    # url(r'^(?P<report_key>[a-z0-9-]+)/?$', views.ReportView.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)
