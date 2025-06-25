from typing import List

from gundi_client_v2.client import GundiClient, GundiDataSenderClient


async def _get_gundi_api_key(integration_id):
    async with GundiClient() as gundi_client:
        return await gundi_client.get_integration_api_key(integration_id=integration_id)


async def _get_sensors_api_client(integration_id):
    gundi_api_key = await _get_gundi_api_key(integration_id=integration_id)
    assert gundi_api_key, f"Cannot get a valid API Key for integration {integration_id}"
    sensors_api_client = GundiDataSenderClient(integration_api_key=gundi_api_key)
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
    sensors_api_client = await _get_sensors_api_client(integration_id=str(integration_id))
    return await sensors_api_client.post_observations(data=observations)
