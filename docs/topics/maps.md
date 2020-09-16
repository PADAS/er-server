EarthRanger Maps
=======================================================

## Basemaps
ER supports displaying basemaps provided by major map creators using Mapbox Technology. We will describe the most commonly supported basemap types, but if you don't find your answer here, contact ER Tech Support with further questions.

Popular map providers support serving maps using what is known as a raster tile service. There is a url pattern to their offering that supports an XYZ pattern. This is used by the ER UI to ask for a map tile for a specific lon/lat/zoom level.
For example here is what an OpenStreetmap tile server url looks like: https://a.tile.openstreetmap.org/${z}/${x}/${y}.png

Basemaps are configured in ER [here](/admin/mapping/tilelayer/)
All basemaps the are added then in turn get displayed in the ER UI. Review them to see the basic configurations we provide out of the box.

We said earlier we support raster tileservers. Specifically in ER we can configure a standard tile server as well as an advanced Mapbox Studio authored tileserver and style.

### Map Layer service Type
#### Tile Server
This is the basic raster XYZ or QUADKEY tileserver. You will need to find the tileserver URL for this service as well as a link to an icon for display in ER.
#### Mapbox Style
For this advanced configuration, we are using a Mapbox Studio generated and hosted map. Go here to log into your mapbox account and find your map in [Studio](https://studio.mapbox.com/)

We need the url to the mapbox style which will be used for the URL as well as the styleUrl. Find this in Mapbox Studio in Share under the Developer section labeled "Style URL"

Use the value from "Style URL" as the URL for a new Basemap configuration in ER. Additionally under "Advanced Tile Layer Attributes" add an entry "styleUrl": "<insert value here>"

TODO: our UI is harcoded to use the ER Mapbox studio token, how do I use a Mapbox Style from my own account that would have a differenct token

## [Map Feature Classes](map_feature_styles.md)
