
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



{{ module }}.init = function() {

    {% block map_options %}// The options hash, w/ zoom, resolution, and projection settings.
    var options = {
        {% autoescape off %}
        {% for item in map_options.items %}
        '{{ item.0 }}' : {{ item.1 }},
        {% endfor %}{% endautoescape %}

    }
{% endblock %}


{{ module }}.get_ewkt = function(feat){
    // console.log("feat", feat)
    return 'SRID={{ srid|unlocalize }};' + {{ module }}.wkt_f.writeFeature(feat);
};

var write_wkt = function(feat) {
    document.getElementById('{{ id }}').value = {{ module }}.get_ewkt(feat);
};

var add_wkt = function (event) {
    // This function will sync the contents of the `vector` layer with the
    // WKT in the text-field
    if(source.getFeatures().length > 1) {
        old_feats = source.getFeatures()[0];
        source.removeFeature(old_feats);
    }
    write_wkt(event.feature)
};



// Modify WKT-TextField
var modify_wkt = function(event) {
    //  When modifying the selected component the vector-layer increment "num_geom" value.
    // var feat = new
    write_wkt(event.feature);


};

// var map = new ol.Map('id_feature_geometry_map', options)

var raster = new ol.layer.Tile({
    source: new ol.source.OSM()
})

var source = new ol.source.Vector();
var vector = new ol.layer.Vector({
    source: source,
    style: new ol.style.Style({
        fill: new ol.style.Fill({
           color: 'rgba(255, 204, 51, 0.3)'
        }),
        stroke: new ol.style.Stroke({
            color: '#65cdcc',
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

    ])
});


// Geometric Object
var createGeometricObject = function(innerHTML, geoType, className){
    var button = document.createElement('button');
    button.innerHTML = innerHTML

    var geometricObject = function(e){
        e.preventDefault()
        map.getInteractions().pop()

        draw = new ol.interaction.Draw({
            source: source,
            type: geoType
        });
        draw.on('drawend', function (event) {
            map.removeInteraction(draw);
        });
        map.addInteraction(draw);
    };

    button.addEventListener('click', geometricObject, false);

    var element = document.createElement('div');
    element.className = `${className} ol-unselectable ol-control`;
    element.appendChild(button);

    var geoControl = new ol.control.Control({
        element: element
    });

    map.addControl(geoControl);
};


// Polygon
var polygonUrl = '<img class="img_1" src="https://img.icons8.com/ios-glyphs/30/ffffff/polygon.png">';
createGeometricObject(polygonUrl, 'Polygon', 'ol-polygon');


// Linestring
var linestringUrl = '<img class="img_1" src="https://img.icons8.com/ios-filled/50/ffffff/polyline.png">';
createGeometricObject(linestringUrl, 'LineString', 'ol-linestring');

// Point
var pointUrl = '<img class="img_2" src="https://img.icons8.com/material-rounded/24/ffffff/filled-circle.png">';
createGeometricObject(pointUrl, 'Point', 'ol-point');


// Modify
var button_modify = document.createElement('button');
button_modify.innerHTML = '<img class="img_1" src="https://img.icons8.com/ios-glyphs/24/ffffff/map-editing--v2.png">';

var modify = function (e) {
    e.preventDefault();
    modify = new ol.interaction.Modify({ source: source });

    map.addInteraction(modify);
};

button_modify.addEventListener('click', modify, false);

var element_modify = document.createElement('div');
element_modify.className = 'ol-modify ol-unselectable ol-control';
element_modify.appendChild(button_modify);

var modifyControl = new ol.control.Control({
    element: element_modify
});
map.addControl(modifyControl);



// map.on('pointermove', function(e) {
//     if (e.dragging) return;
//     var pixel = map.getEventPixel(e.originalEvent)
//     var hit = map.hasFeatureAtPixel(pixel);
//     console.log(hit)
//     map.getTargetElement().style.cursor = hit ? 'pointer': '';
// });


var zoomslider = new ol.control.ZoomSlider();
map.addControl(zoomslider);

var scaleline = new ol.control.ScaleLine();
map.addControl(scaleline);

var dragrotate = new ol.interaction.DragRotateAndZoom()
map.addInteraction(dragrotate);


/**
 * Handle change event.
 */


var wkt = document.getElementById("{{ id }}");

vector.getSource().on("addfeature", add_wkt)
vector.getSource().on("changefeature", modify_wkt)
// vector.getSource().on("change", modify_wkt);

// if(wkt) {
//     // OpenLayers cannot handle EWKT -- we make sure to strip it out.
//     // EWKT is only exposed to OL if there's a validation error in the admin.
//     // var match = {{ module }}.re.exec(wkt);
//     var wkt_value = wkt.value;
//     admin_geom = {{ module }}.wkt_f.readFeature(wkt_value);
//     // console.log(admin_geom)
//     write_wkt(admin_geom);
//     // source.addFeatures()

//     source.addFeatures([admin_geom]);

// };

};



