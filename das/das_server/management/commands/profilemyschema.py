from cProfile import Profile

import django.contrib.auth
from django.core.management.base import BaseCommand
from django.http.request import HttpRequest
from django.utils.module_loading import import_string

from utils.tenant.commands import TenantCommandMixin

User = django.contrib.auth.get_user_model()

from rest_framework import renderers
from rest_framework.request import Request
from rest_framework.schemas.openapi import SchemaGenerator


class Command(TenantCommandMixin, BaseCommand):
    help = "Generates configured API schema for project."

    def add_arguments(self, parser):
        parser.add_argument("--title", dest="title", default="", type=str)
        parser.add_argument("--url", dest="url", default=None, type=str)
        parser.add_argument("--description", dest="description", default=None, type=str)
        parser.add_argument("--format", dest="format", choices=["openapi", "openapi-json"], default="openapi", type=str)
        parser.add_argument("--urlconf", dest="urlconf", default=None, type=str)
        parser.add_argument("--generator_class", dest="generator_class", default=None, type=str)
        parser.add_argument("--file", dest="file", default=None, type=str)
        parser.add_argument("--username", dest="username", default=None, type=str)
        parser.add_argument("--profile_file", dest="profile_file", default="myschema.profile", type=str)

    def handle(self, *args, **options):
        profiler = Profile()
        profiler.runcall(self._handle, *args, **options)
        profiler.dump_stats(options["profile_file"])

    def _handle(self, *args, **options):
        if options["generator_class"]:
            generator_class = import_string(options["generator_class"])
        else:
            generator_class = SchemaGenerator
        generator = generator_class(
            url=options["url"],
            title=options["title"],
            description=options["description"],
            urlconf=options["urlconf"],
        )
        request = None
        if options["username"]:
            request = Request(HttpRequest())
            request.user = User.objects.get(username=options["username"])
        schema = generator.get_schema(request=request, public=not bool(request))
        renderer = self.get_renderer(options["format"])
        output = renderer.render(schema, renderer_context={})

        if options["file"]:
            with open(options["file"], "wb") as f:
                f.write(output)
        else:
            self.stdout.write(output.decode())

    def get_renderer(self, format):
        renderer_cls = {
            "openapi": renderers.OpenAPIRenderer,
            "openapi-json": renderers.JSONOpenAPIRenderer,
        }[format]
        return renderer_cls()
