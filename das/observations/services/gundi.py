import logging
from typing import List

from gundi_client_v2.client import GundiClient, GundiDataSenderClient

logger = logging.getLogger(__name__)


async def _get_gundi_api_key(integration_id):
    async with GundiClient() as gundi_client:
        return await gundi_client.get_integration_api_key(integration_id=integration_id)


async def _get_sensors_api_client(integration_id, sensors_api_base_url):
    gundi_api_key = await _get_gundi_api_key(integration_id=integration_id)
    if not gundi_api_key:
        raise ValueError(f"Cannot get a valid API Key for integration {integration_id}")

    if not sensors_api_base_url:
        raise ValueError("sensors_api_base_url is required but was not provided")

    if not isinstance(sensors_api_base_url, str):
        raise ValueError(f"sensors_api_base_url must be a string, got {type(sensors_api_base_url)}")

    if not sensors_api_base_url.startswith(("http://", "https://")):
        raise ValueError(f"sensors_api_base_url must start with 'http://' or 'https://'. Got: {sensors_api_base_url}")

    sensors_api_client = GundiDataSenderClient(
        integration_api_key=gundi_api_key, sensors_api_base_url=sensors_api_base_url
    )

    logger.info(f"Instantiated GundiDataSenderClient with URL {sensors_api_client.sensors_api_endpoint}")
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
        integration_id=str(integration_id), sensors_api_base_url=kwargs.get("sensors_api_base_url")
    )
    return await sensors_api_client.post_observations(data=observations)
