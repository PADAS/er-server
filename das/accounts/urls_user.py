from django.contrib.auth import login, logout, views
from django.urls import re_path

from utils.constants import regex

urlpatterns = [
    re_path(r"^login/?$", login, name="login"),
    re_path(r"^logout/?$", logout, name="logout"),
    re_path(
        r"^password_change/?$",
        views.PasswordChangeView.as_view(),
        name="password_change",
    ),
    re_path(
        r"^password_change/done/?$",
        views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    re_path(
        r"^password_reset/?$", views.PasswordResetView.as_view(), name="password_reset"
    ),
    re_path(
        r"^password_reset/done/?$",
        views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    re_path(
        rf"^reset/(?P<uidb64>{regex.UIDB64})/(?P<token>{regex.TOKEN})/?$",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    re_path(
        r"^reset/done/?$",
        views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
