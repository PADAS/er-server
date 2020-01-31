from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from django.contrib.auth import get_user_model

from accounts.models import User
from core.models import TimestampedModel


class UserAgreement(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='userterms',
                             on_delete=models.CASCADE)
    eula = models.ForeignKey('EULA', related_name='userterms',
                             on_delete=models.CASCADE)

    date_accepted = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Date Accepted")
    )

    accepted = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "eula")


class EULAManager(models.Manager):
    def get_active_eula(self):
        return self.get_queryset().get(active=True)

    def has_user_accepted_active_eula(self, user):
        # TODO 30/01/2020 complete this logic
        return False

    def get_users_that_have_accepted_the_latest_eula(self):
        latest = self.get_queryset().get(active=True)
        return latest.users.all()

    def get_users_that_have_not_accepted_latest_eula(self):
        accepted_users = self.get_users_that_have_accepted_the_latest_eula()
        return get_user_model.objects.exclude(accepted_users)

    def accept_eula(self, user):
        UserAgreement.objects.create


class EULA(TimestampedModel):
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through=UserAgreement, blank=True
    )
    version_number = models.DecimalField(default=1.0, decimal_places=1,
                                         max_digits=2, unique=True)
    content = models.TextField(null=True, blank=True, help_text=_(
        "Provide users with some info about what's changed and why"), )
    active = models.BooleanField(default=False)

    objects = EULAManager()

    def __str__(self):
        return "EULA v" + str(self.version_number)

    def save(self, *args, **kwargs):
        """
        Make sure we only have one active EULA version in the DB
        """
        self.active = True
        with transaction.atomic():
            EULA.objects.filter(active=True).update(active=False)
            return super(EULA, self).save(*args, **kwargs)
