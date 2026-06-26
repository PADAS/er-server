from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.core.management.base import BaseCommand, CommandError
from django.http import HttpRequest

from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin


class CommandRequest(HttpRequest):
    def _get_scheme(self):
        return "https"


class Command(TenantCommandMixin, BaseCommand):
    help = "Send a password reset email to a specified user"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username of the user to send the password reset email to")

    def handle(self, *args, **options):
        tenant_settings = get_tenant_settings()
        request = CommandRequest()
        request.META["HTTP_HOST"] = tenant_settings.domain

        User = get_user_model()

        username = options["username"]
        try:
            # Find the user by email
            user = User.objects.get(username=username)
            form = PasswordResetForm(data={"email": user.email})
            assert form.is_valid()

            opts = {
                "email_template_name": "registration/password_reset_email.html",
                "html_email_template_name": "registration/password_reset_email_html.html",
                "from_email": settings.DEFAULT_FROM_EMAIL,
                "request": request,
                "subject_template_name": "registration/password_reset_subject.txt",
                "use_https": request.is_secure(),
            }

            form.save(**opts)

            self.stdout.write(self.style.SUCCESS(f"Password reset email sent to {username} at {user.email}"))

        except User.DoesNotExist:
            raise CommandError(f"User {username} does not exist")
