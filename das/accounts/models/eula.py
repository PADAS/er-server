import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from django.contrib.auth import get_user_model

from core.models import TimestampedModel


class UserAgreement(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='userterms',
                             on_delete=models.CASCADE)
    eula = models.ForeignKey('EULA', related_name='userterms',
                             on_delete=models.CASCADE)

    date_accepted = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Date Accepted")
    )

    accept = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "eula")

    def save(self, *args, **kwargs):
        self.accept = True
        user_agreement = super(UserAgreement, self).save(*args, **kwargs)
        user = self.user
        if not user.accepted_eula:
            user.accepted_eula = True
            user.save()
        return user_agreement


class EULAManager(models.Manager):
    def get_active_eula(self):
        return self.get_queryset().get(active=True)

    def get_users_that_have_accepted_the_latest_eula(self):
        active_eula = self.get_queryset().get(active=True)
        return active_eula.users.all()

    def get_users_that_have_not_accepted_latest_eula(self):
        accepted_users = self.get_users_that_have_accepted_the_latest_eula()
        return get_user_model().objects.exclude(id__in=[user.id for user in accepted_users])

    def accept_eula(self, user):
        active_eula = self.get_queryset().get(active=True)
        UserAgreement.objects.create(user=user, eula=active_eula, accept=True)
        user.accepted_eula = True
        user.save()


class EULA(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid1)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through=UserAgreement, blank=True
    )
    version = models.CharField(max_length=30, unique=True)
    eula_url = models.URLField(null=False, blank=False)
    active = models.BooleanField(default=False)

    objects = EULAManager()

    def __str__(self):
        return self.version

    def save(self, *args, **kwargs):
        """
        Make sure we only have one active EULA version in the DB
        """
        self.active = True
        with transaction.atomic():
            EULA.objects.filter(active=True).update(active=False)
            return super(EULA, self).save(*args, **kwargs)
