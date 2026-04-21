import pytest

from django.contrib.admin import site as admin_site
from django.test import RequestFactory

from factories import SubjectFactory
from observations.admin import SubjectAdmin
from observations.models import Subject


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_subject_admin_delete_queryset_with_distinct(superuser):
    """
    SubjectAdmin.get_queryset returns a .distinct() queryset (needed to avoid
    duplicate rows when M2M/join filters are active).  Django forbids calling
    .delete() on a distinct queryset, so delete_queryset must work around that.
    """
    subject1 = SubjectFactory()
    subject2 = SubjectFactory()

    admin_instance = SubjectAdmin(model=Subject, admin_site=admin_site)
    request = RequestFactory().get("/")
    request.user = superuser

    # Simulate exactly what Django's admin delete action does:
    # get_queryset() returns a .distinct() queryset, which is passed to delete_queryset()
    selected = admin_instance.get_queryset(request).filter(pk__in=[subject1.pk, subject2.pk])
    assert selected.query.distinct, "precondition: selected queryset must have distinct to reproduce the bug"

    # Should not raise "Cannot call delete() after .distinct()"
    admin_instance.delete_queryset(request, selected)

    assert not Subject.objects.filter(pk__in=[subject1.pk, subject2.pk]).exists()
