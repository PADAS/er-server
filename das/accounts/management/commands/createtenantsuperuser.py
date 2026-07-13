from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.management.commands.createsuperuser import (
    Command as CreateSuperuserCommand,
)
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError, CommandParser
from django.db.models import Field

from accounts.models import User, UserManager
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, CreateSuperuserCommand):
    def _get_user_model(self) -> type[User]:
        # django-stubs types self.UserModel as type[AbstractBaseUser] (get_user_model()'s
        # declared return type), which doesn't carry USERNAME_FIELD, the email/auth0_id
        # fields, or the tenant-aware `objects` manager. AUTH_USER_MODEL is always
        # accounts.User in this codebase (see das_server/settings.py), so assert that and
        # hand back a properly narrowed reference for the rest of this command to use.
        assert issubclass(self.UserModel, User), "AUTH_USER_MODEL must be accounts.models.User"
        return self.UserModel

    def _get_manager(self, user_model: type[User], database: str) -> UserManager:
        # user_model.objects degrades to the generic `Manager[User]` under the type
        # checker: django-stubs' Manager descriptor `__get__` overload returns a bare
        # `BaseManager`, discarding the concrete UserManager subtype (get_by_natural_key,
        # normalize_email) actually assigned on the model. UserManager is the only manager
        # Django instantiates for this model (accounts/models/user.py), so this cast just
        # tells the checker what's true at runtime.
        manager = cast(UserManager, user_model.objects)
        return manager.db_manager(database)

    def _clean_char_field(self, user_model: type[User], field_name: str, value: str) -> str:
        field = user_model._meta.get_field(field_name)
        # _meta.get_field() can return a ForeignObjectRel/GenericForeignKey for reverse
        # relations, neither of which has .clean(); both email and auth0_id are concrete
        # model fields, so this always holds.
        assert isinstance(field, Field), f"{field_name} must be a concrete model field"
        try:
            return field.clean(value, None)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        user_model = self._get_user_model()
        parser.add_argument(
            "--email",
            help=(
                "Specifies the email address for the superuser. The User model does not "
                "declare email as a required field, so this is only applied when the "
                f"--{user_model.USERNAME_FIELD} is supplied explicitly on the command "
                "line (e.g. together with --noinput); it is rejected otherwise, since the "
                "username actually assigned during an interactive prompt or via the "
                f"DJANGO_SUPERUSER_{user_model.USERNAME_FIELD.upper()} environment "
                "variable cannot be recovered afterwards."
            ),
        )
        parser.add_argument(
            "--auth0_id",
            help=(
                "Specifies the Auth0 subject identifier (sub claim) for the superuser. Must "
                "be unique per tenant. Like --email, this is only applied when the "
                f"--{user_model.USERNAME_FIELD} is supplied explicitly on the command line; "
                "it is rejected otherwise, since the username actually assigned during an "
                "interactive prompt or via the "
                f"DJANGO_SUPERUSER_{user_model.USERNAME_FIELD.upper()} environment variable "
                "cannot be recovered afterwards."
            ),
        )
        parser.add_argument(
            "--update",
            action="store_true",
            default=False,
            help=(
                f"If a user with the given --{user_model.USERNAME_FIELD} already exists for "
                "this tenant, update it in place instead of failing: --email/--auth0_id (if "
                "given) are applied and is_superuser/is_staff are (re)set to True; the "
                "password is left untouched. Without --update, an already-existing "
                f"{user_model.USERNAME_FIELD} raises an error instead of being modified. "
                f"Like --email and --auth0_id, this requires --{user_model.USERNAME_FIELD} "
                "to be specified explicitly on the command line, for the same reason."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> str | None:
        user_model = self._get_user_model()

        # Pop these out before delegating: the parent command only knows about
        # USERNAME_FIELD + REQUIRED_FIELDS, and the User model's REQUIRED_FIELDS is
        # empty, so these unrecognized options would never reach create_superuser.
        email = options.pop("email", None)
        auth0_id = options.pop("auth0_id", None)
        update = options.pop("update", False)
        cleaned_email: str | None = None
        cleaned_auth0_id: str | None = None

        provided_flags: list[str] = []
        if email is not None:
            provided_flags.append("--email")
        if auth0_id is not None:
            provided_flags.append("--auth0_id")
        if update:
            provided_flags.append("--update")

        username: str | None = options.get(user_model.USERNAME_FIELD)
        if provided_flags and not username:
            raise CommandError(
                f"{' / '.join(provided_flags)} requires --{user_model.USERNAME_FIELD} to "
                "be specified explicitly on the command line; it cannot be combined with "
                "an interactively-entered username or one supplied via the "
                f"DJANGO_SUPERUSER_{user_model.USERNAME_FIELD.upper()} environment "
                "variable."
            )

        # Validate everything up front, before super().handle() creates (or, in the
        # IntegrityError case below, fails to create) the user: raising afterward would
        # leave a half-done superuser behind.
        manager: UserManager | None = None
        existing_user_exists = False
        if username:
            # The composite UniqueConstraint(["das_tenant", "username"]) doesn't register
            # as a single-field unique constraint, so Django's own createsuperuser skips
            # its duplicate-username check here and would otherwise let this fall through
            # to a raw IntegrityError.
            manager = self._get_manager(user_model, options["database"])
            existing_user_exists = manager.filter(username=username).exists()
            if existing_user_exists and not update:
                raise CommandError(
                    f"A user with username {username!r} already exists for this tenant. " "Pass --update to modify it."
                )

        if email is not None:
            if not email.strip():
                raise CommandError(
                    "--email cannot be empty or whitespace-only; omit the option " "entirely to leave email unset."
                )
            cleaned_email = self._clean_char_field(user_model, "email", email)
            assert manager is not None  # username is required whenever email is given
            # Normalize before querying: the value actually saved below is
            # manager.normalize_email(cleaned_email), so the pre-check must compare against
            # that same normalized form or it can miss an existing row that only differs in
            # domain case (e.g. "dup@EXAMPLE.com" vs. the stored "dup@example.com").
            cleaned_email = manager.normalize_email(cleaned_email)
            email_qs = manager.filter(email=cleaned_email)
            if existing_user_exists:
                email_qs = email_qs.exclude(username=username)
            if email_qs.exists():
                raise CommandError(f"A user with email {cleaned_email!r} already exists for this tenant.")

        if auth0_id is not None:
            if not auth0_id.strip():
                raise CommandError(
                    "--auth0_id cannot be empty or whitespace-only; omit the option "
                    "entirely to leave auth0_id unset."
                )
            cleaned_auth0_id = self._clean_char_field(user_model, "auth0_id", auth0_id)
            assert manager is not None  # username is required whenever auth0_id is given
            auth0_qs = manager.filter(auth0_id=cleaned_auth0_id)
            if existing_user_exists:
                auth0_qs = auth0_qs.exclude(username=username)
            if auth0_qs.exists():
                raise CommandError(f"A user with auth0_id {cleaned_auth0_id!r} already exists for this " "tenant.")

        if update and existing_user_exists:
            assert username is not None
            assert manager is not None
            user = manager.get_by_natural_key(username)

            update_fields: list[str] = []
            if email is not None and user.email != cleaned_email:
                user.email = cleaned_email
                update_fields.append("email")
            if auth0_id is not None and user.auth0_id != cleaned_auth0_id:
                user.auth0_id = cleaned_auth0_id
                update_fields.append("auth0_id")
            if not user.is_superuser:
                user.is_superuser = True
                update_fields.append("is_superuser")
            if not user.is_staff:
                user.is_staff = True
                update_fields.append("is_staff")

            if update_fields:
                user.save(update_fields=update_fields)
            self.stdout.write(f"Updated existing superuser {username!r}.")
            return None

        result = super().handle(*args, **options)

        # --update alone (with neither --email nor --auth0_id) is a valid, idempotent upsert
        # invocation on a --username that doesn't exist yet: it lands here with provided_flags
        # non-empty but nothing to apply, so there is no update_fields save to perform.
        if email is None and auth0_id is None:
            return result

        assert username is not None  # guaranteed by the CommandError check above
        assert manager is not None
        user = manager.get_by_natural_key(username)

        update_fields = []
        if email is not None:
            user.email = cleaned_email
            update_fields.append("email")
        if auth0_id is not None:
            user.auth0_id = cleaned_auth0_id
            update_fields.append("auth0_id")

        user.save(update_fields=update_fields)
        return result
