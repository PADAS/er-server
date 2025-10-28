import json
import logging
from typing import List

import requests
from gundi_client_v2.client import GundiClient, GundiDataSenderClient

logger = logging.getLogger(__name__)


async def _get_gundi_api_key(integration_id, gundi_api_base_url):
    async with GundiClient(base_url=gundi_api_base_url) as gundi_client:
        return await gundi_client.get_integration_api_key(integration_id=integration_id)


async def _get_sensors_api_client(integration_id, sensors_api_base_url, gundi_api_base_url):
    gundi_api_key = await _get_gundi_api_key(integration_id=integration_id, gundi_api_base_url=gundi_api_base_url)
    if not gundi_api_key:
        raise ValueError(f"Cannot get a valid API Key for integration {integration_id}")

    if not sensors_api_base_url:
        raise ValueError("sensors_api_base_url is required but was not provided")

    if not isinstance(sensors_api_base_url, str):
        raise ValueError(f"sensors_api_base_url must be a string, got {type(sensors_api_base_url)}")

    if not sensors_api_base_url.startswith(("http://", "https://")):
        raise ValueError(f"sensors_api_base_url must start with 'http://' or 'https://'. Got: {sensors_api_base_url}")

    sensors_api_client = GundiDataSenderClient(
        integration_api_key=gundi_api_key,
        sensors_api_base_url="https://sensors.api.stage.gundiservice.org",
    )

    return sensors_api_client


async def send_observations_to_gundi(observations: List[dict], **kwargs) -> dict:
    """
    Send Observations to Gundi using the REST API v2
    :param observations: A list of observations in the following format:
    [
        {
            "source": "collar-xy123",
            "type": "tracking-device",
            "subject_type": "puma",
            "recorded_at": "2024-01-24 09:03:00-0300",
            "location": {
                "lat": -51.748,
                "lon": -72.720
            },
            "additional": {
                "speed_kmph": 10
            }
        },
        ...
    ]
    :param kwargs: integration_id: The UUID of the related integration
    :return: A dict with the response from the API
    """
    integration_id = kwargs.get("integration_id")
    assert integration_id, "integration_id is required"
    sensors_api_client = await _get_sensors_api_client(
        integration_id=str(integration_id),
        sensors_api_base_url=kwargs.get("sensors_api_base_url"),
        gundi_api_base_url=kwargs.get("gundi_api_base_url"),
    )
    return await sensors_api_client.post_observations(data=observations)


def _get_gundi_api_key_sync(integration_id: str, gundi_api_base_url: str) -> str:
    """
    Get API key for a Gundi integration using synchronous HTTP call.

    :param integration_id: UUID of the Gundi integration
    :param gundi_api_base_url: Base URL for the Gundi API
    :return: API key string
    """
    from gundi_client_v2 import settings as gundi_settings

    # Get OAuth token
    token_url = gundi_settings.OAUTH_TOKEN_URL
    client_id = gundi_settings.KEYCLOAK_CLIENT_ID
    client_secret = gundi_settings.KEYCLOAK_CLIENT_SECRET
    audience = gundi_settings.KEYCLOAK_AUDIENCE

    # Request OAuth token
    token_response = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
        },
        timeout=30,
    )
    token_response.raise_for_status()
    token_data = token_response.json()
    access_token = token_data.get("access_token")
    token_type = token_data.get("token_type", "Bearer")

    # Get API key from Gundi
    api_key_url = f"{gundi_api_base_url}/v2/integrations/{integration_id}/api-key/"
    headers = {"authorization": f"{token_type} {access_token}"}

    api_key_response = requests.get(api_key_url, headers=headers, timeout=30)
    api_key_response.raise_for_status()

    return api_key_response.json().get("api_key")


def send_observations_to_gundi_sync(
    observations: List[dict], integration_id: str, sensors_api_base_url: str, gundi_api_base_url: str
) -> dict:
    """
    Send observations to Gundi using synchronous HTTP calls.

    :param observations: A list of observations in the following format:
    [
        {
            "source": "collar-xy123",
            "type": "tracking-device",
            "subject_type": "puma",
            "recorded_at": "2024-01-24 09:03:00-0300",
            "location": {
                "lat": -51.748,
                "lon": -72.720
            },
            "additional": {
                "speed_kmph": 10
            }
        },
        ...
    ]
    :param integration_id: UUID of the Gundi integration
    :param sensors_api_base_url: Base URL for the Sensors API
    :param gundi_api_base_url: Base URL for the Gundi API
    :return: Response from the API as a dictionary
    """
    # Get API key
    api_key = _get_gundi_api_key_sync(integration_id, gundi_api_base_url)

    if not api_key:
        raise ValueError(f"Cannot get a valid API Key for integration {integration_id}")

    # Prepare data
    clean_batch = [json.loads(json.dumps(obs, default=str)) for obs in observations]

    # Send observations
    url = f"{sensors_api_base_url}/v2/observations/"
    headers = {"apikey": api_key}

    response = requests.post(url, json=clean_batch, headers=headers, timeout=120)
    response.raise_for_status()

    return response.json()
