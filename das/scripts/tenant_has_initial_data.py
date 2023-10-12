from django.contrib.auth import get_user_model
from django.core.management import CommandError

from activity.models import Event
from observations.models import Subject
from utils.tenant import set_tenant

User = get_user_model()


def run(*args):
    domain = args[0]
    if not domain:
        raise CommandError("Specify the tenant domain as the first commandline argument", returncode=2)

    set_tenant(domain)
    if User.objects.filter(username="admin").exists() or Event.objects.all().exists() or Subject.objects.all().exists():
        return 0

    return 1
