from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_django_42"),
    ]

    operations = [
        migrations.AddField(
            model_name="dasapplication",
            name="bypass_auth0",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When True, this application's OAuth2 tokens bypass Auth0 JWT "
                    "enforcement on tenants with require_idp=True."
                ),
            ),
        ),
    ]
