# Since this package contains a "django" module, this is required on Python 2.
from __future__ import absolute_import

import io
import sys

import jinja2
import six

from django.conf import settings
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.template.backends.base import BaseEngine
from django.template.backends.utils import csrf_input_lazy, csrf_token_lazy
from django.utils.module_loading import import_string

from reports.loaders import DocxFileSystemLoader


class DocxBackend(BaseEngine):

    app_dirname = 'docx_template'

    def __init__(self, params):
        params = params.copy()
        options = params.pop('OPTIONS').copy()
        super(DocxBackend, self).__init__(params)

        environment = options.pop(
            'environment',
            'reports.environment.Environment'
        )
        environment_cls = import_string(environment)

        options.setdefault('autoescape', True)
        options.setdefault('loader', DocxFileSystemLoader(self.template_dirs))
        options.setdefault('auto_reload', settings.DEBUG)
        options.setdefault('undefined',
                           jinja2.DebugUndefined if settings.DEBUG else jinja2.Undefined)

        self.env = environment_cls(**options)

    def from_string(self, template_code):
        return Template(self.env.from_string(template_code))

    def get_template(self, template_name):
        try:

            template = self.env.get_template(template_name)
            return Template(template)
        except jinja2.TemplateNotFound as exc:
            six.reraise(
                TemplateDoesNotExist,
                TemplateDoesNotExist(exc.name, backend=self),
                sys.exc_info()[2],
            )
        except jinja2.TemplateSyntaxError as exc:
            new = TemplateSyntaxError(exc.args)
            new.template_debug = get_exception_info(exc)
            six.reraise(TemplateSyntaxError, new, sys.exc_info()[2])
        except Exception:
            raise


class Template(object):

    def __init__(self, template):
        self.template = template
        self.origin = Origin(
            # TODO: I've punted on
            # name=template.filename, template_name=template.name,
            name='somefilename', template_name='sometemplatename',
        )

    def render(self, context=None, request=None):
        if context is None:
            context = {}
        if request is not None:
            context['request'] = request
            context['csrf_input'] = csrf_input_lazy(request)
            context['csrf_token'] = csrf_token_lazy(request)

        self.template.render(context)

        try:
            os = io.BytesIO()
            self.template.save(os)
            os.seek(0)
            return os.read()
        except Exception as e:
            print(e)


class Origin(object):
    """
    A container to hold debug information as described in the template API
    documentation.
    """

    def __init__(self, name, template_name):
        self.name = name
        self.template_name = template_name


def get_exception_info(exception):
    """
    Formats exception information for display on the debug page using the
    structure described in the template API documentation.
    """
    context_lines = 10
    lineno = exception.lineno
    lines = list(enumerate(exception.source.strip().split("\n"), start=1))
    during = lines[lineno - 1][1]
    total = len(lines)
    top = max(0, lineno - context_lines - 1)
    bottom = min(total, lineno + context_lines)

    return {
        'name': exception.filename,
        'message': exception.message,
        'source_lines': lines[top:bottom],
        'line': lineno,
        'before': '',
        'during': during,
        'after': '',
        'total': total,
        'top': top,
        'bottom': bottom,
    }
