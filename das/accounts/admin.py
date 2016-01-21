from __future__ import unicode_literals


from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin


from accounts.models import User


class UserAdmin(DjangoUserAdmin):
    pass


# If the model has been swapped, this is basically a noop.
admin.site.register(User, UserAdmin)
