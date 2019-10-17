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

var raster = new ol.layer.Tile({
    source: new ol.source.OSM()
})

var source = new ol.source.Vector();
var vector = new ol.layer.Vector({
    source: source,
    style: new ol.style.Style({
        fill: new ol.style.Fill({
            color: 'rgba(255, 255, 255, 0.2)'
        }),
        stroke: new ol.style.Stroke({
            color: '#ffcc33',
            width: 2
        }),
        image: new ol.style.Circle({
            radius: 7,
            fill: new ol.style.Fill({
                color: '#ffcc33'
            })
        })
    })
});



var map = new ol.Map({
    view: new ol.View({
        center: [0, 0],
        maxResolution: options.maxResolution,
        zoom: 3,
        projection: options.projection.projection_
    }),
    layers: [raster, vector],
    target: '{{ id }}_map',
    controls: new ol.control.defaults().extend([
        new ol.control.FullScreen()
    ]),

    // interactions: new ol.interaction.defaults().extend([
    //     new ol.interaction.DragRotateAndZoom(),
    // ]),


});


var modify = new ol.interaction.Modify({ source: source });
map.addInteraction(modify);

var draw, snap; // global so we can remove them later
var typeSelect = document.getElementById('type');


function addInteractions() {
    draw = new ol.interaction.Draw({
        source: source,
        type: typeSelect.value
    });
    map.addInteraction(draw);
    snap = new ol.interaction.Snap({ source: source });
    map.addInteraction(snap);

}

var dragrotate = new ol.interaction.DragRotateAndZoom()
map.addInteraction(dragrotate)


/**
 * Handle change event.
 */
typeSelect.onchange = function () {
    map.removeInteraction(draw);
    map.removeInteraction(snap);
    addInteractions();
};

addInteractions();



{% endblock %}



};