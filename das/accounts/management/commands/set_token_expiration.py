import logging

from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from oauth2_provider.models import AccessToken

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '''
    Set expiration for an Access Token matching the provided prefix.
    If more than one prefix is found to match, this will do nothing.
    '''

    def add_arguments(self, parser):
        parser.add_argument('-t', '--token_prefix', type=str, required=True,
                            help='A token with this prefix will be updated.')

        parser.add_argument('-x', '--expire_at', type=str, default=None,
                            help='Use this date when updating a token\'s expiration.')

    def handle(self, *args, **options):
        set_token_expiration(token_prefix=options['token_prefix'], expire_at=options['expire_at'])


def set_token_expiration(token_prefix=None, expire_at=None):
    if not token_prefix:
        raise ValueError('You must provide an access token prefix')

    if expire_at:
        expire_at = dateutil.parser.parse(expire_at)
        if not expire_at.tzinfo:
            expire_at = expire_at.replace(tzinfo=timezone.utc)
    else:
        expire_at = datetime.now(tz=timezone.utc)

    try:
        ac = AccessToken.objects.get(token__startswith=token_prefix)
        ac.expires = expire_at
        ac.save()
        logger.info(f'Found token with prefix "{token_prefix}" for username {ac.user.username}.'
                    f' It now expires at {expire_at.isoformat()}')

    except AccessToken.DoesNotExist:
        logger.warning(f'No access token found for prefix "{token_prefix}". Doing nothing.')
    except AccessToken.MultipleObjectsReturned:
        logger.warning(f'Multiple tokens found for prefix "{token_prefix}". Doing nothing.')
