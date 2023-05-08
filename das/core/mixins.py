from django.conf import settings

from mapping.models import TileLayer


class TileLayersMixin:
    TOKENS = {"Mapbox Satellite Map": settings.MAPBOX_TOKEN}

    def _get_tile_layers(self):
        layers = []
        for configuration in TileLayer.objects.values("attributes"):
            attributes = configuration["attributes"]
            title = attributes.get("title")
            if title in self.TOKENS:
                url = attributes["url"]
                configuration["attributes"]["url"] = self._get_url(title, url)
            layers.append(configuration)
        return layers

    def _get_url(self, title: str, url: str) -> str:
        token = self.TOKENS[title]
        return f"{url}?access_token={token}"
