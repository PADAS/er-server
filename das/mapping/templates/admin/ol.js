{% load l10n %}

{% block vars %}
var {{ module }} = {};
{{ module }}.map = null; {{ module }}.controls = null; {{ module }}.panel = null; {{ module }}.re = new RegExp("^SRID=\\d+;(.+)", "i"); {{ module }}.layers = {};
{{ module }}.modifiable = {{ modifiable|yesno:"true,false" }};
{{ module }}.wkt_f = new ol.format.WKT();
{{ module }}.is_collection = {{ is_collection|yesno:"true,false" }};
{{ module }}.collection_type = '{{ collection_type }}';
{{ module }}.is_generic = {{ is_generic|yesno:"true,false" }};
{{ module }}.is_linestring = {{ is_linestring|yesno:"true,false" }};
{{ module }}.is_polygon = {{ is_polygon|yesno:"true,false" }};
{{ module }}.is_point = {{ is_point|yesno:"true,false" }};
{% endblock %}


// function getMinZoom() {
//     var width = vie
// }







{{ module }}.init = function() {

    {% block map_options %}// The options hash, w/ zoom, resolution, and projection settings.
    var options = {
        {% autoescape off %}
        {% for item in map_options.items %}
        '{{ item.0 }}' : {{ item.1 }},
        {% endfor %}{% endautoescape %}

    }
{% endblock %}

console.log(options)

// {% block map_creation %}
// var map = new ol.Map({
//     view: new ol.View({
//         center: [0, 0],
//         zoom: 1
//     }),
//     layers: [
//         new ol.layer.Tile({
//             source: new ol.source.OSM()
//         })
//     ],
//     target: 'id_feature_geometry_map'
// });

// var map = new ol.Map('id_feature_geometry_map', options)

var map = new ol.Map({
    view: new ol.View({
        center: [0, 0],
        maxResolution: options.maxResolution,
        zoom: 3
        projection: 
    }),
    layers: [
        new ol.layer.Tile({
            source: new ol.source.OSM()
        })
    ],
    target: '{{ id }}_map',


});






{% endblock %}



};