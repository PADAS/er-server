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


{{ module }}.modify_wkt = function(event){
    if ({{ module }}.is_collection){
        if ({{ module }}.is_point){
            {{ module }}.add_wkt(event);
            return;
        } else {
            // When modifying the selected components are added to the
            // vector layer so we only increment to the `num_geom` value.
            var feat = new OpenLayers.Feature.Vector(new OpenLayers.Geometry.{{ geom_type }}());
            for (var i = 0; i < {{ module }}.num_geom; i++){
                feat.geometry.addComponents([{{ module }}.layers.vector.features[i].geometry]);
            }
            {{ module }}.write_wkt(feat);
        }
    } else {
        {{ module }}.write_wkt(event.feature);
    }
};


{{ module }}.enableDrawing = function(){
};


// Add Select control
// {{ module }}.addSelectControl = function(){
//     // var select = new OpenLayers.Control.SelectFeature({{ module }}.layers.vector, {'toggle' : true, 'clickout' : true});
//     // {{ module }}.map.addControl(select);
//     // select.activate();
// };



// Create an array of controls based on geometry type
{{ module }}.getControls = function(lyr){
    // {{ module }}.panel = new OpenLayers.Control.Panel({'displayClass': 'olControlEditingToolbar'})

    var source = lyr

 var modify = new ol.interaction.Modify({ source: source });
 {{ module }}.map.addInteraction(modify);

 var draw, snap; // global so we can remove them later
var typeSelect = document.getElementById('type');


function addInteractions() {
draw = new ol.interaction.Draw({
         source: source,
         type: typeSelect.value
     });
     {{ module }}.map.addInteraction(draw);
     snap = new ol.interaction.Snap({ source: source });
     {{ module }}.map.addInteraction(snap);


   return addInteractions()
 }


/**
 * Handle change event.
 */
// typeSelect.onchange = function () {
//     {{ module }}.map.removeInteraction(draw);
//     {{ module }}.map.removeInteraction(snap);
//     addInteractions();
// };



};

{{ module }}.init = function() {

//     {% block map_options %}// The options hash, w/ zoom, resolution, and projection settings.
//     var options = {
//         {% autoescape off %}
//         {% for item in map_options.items %}
//         '{{ item.0 }}' : {{ item.1 }},
//         {% endfor %}{% endautoescape %}

//     }
// {% endblock %}




 // The admin map for this geometry field.
 {% block map_creation %}
{{ module }}.map = new ol.Map({
    view: new ol.View({
        center: [{{ default_lon }}, {{ default_lat }}],
        zoom: {{ default_zoom }}
    }),
    target: '{{ id }}_map',
    controls: new ol.control.defaults().extend([
        new ol.control.FullScreen()
    ]),

    interactions: new ol.interaction.defaults().extend([
        new ol.interaction.DragRotateAndZoom(),
    ]),
});


{{ module }}.layers = new ol.layer.Tile({
    source: new ol.source.OSM()
});

{{ module }}.map.addLayer({{ module }}.layers);

{% endblock%}

{% block extra_layers %}{% endblock %}


var source = new ol.source.Vector();

{{ module }}.layers.vector = new ol.layer.Vector({
    source: source,
    style: new ol.style.Style({
        fill: new ol.style.Fill({
            color: 'rgba(255, 204, 51, 0.3)'
        }),
        stroke: new ol.style.Stroke({
            color: '#65cdcc',
            width: 3
        })

    })
});


{{ module }}.map.addLayer({{ module }}.layers.vector);

// Read WKT from the text field:
var wkt = document.getElementById('{{ id }}').value;

if (wkt) {
    // After reading into geometry, immediately write back to
    // WKT <textarea> as EWKT (so that SRID is included).

    var admin_geom = {{ module }}.read_wkt(wkt);
    {{ module }}.write_wkt(admin_geom);

    if ({{ module }}.is_collection){
         // If geometry collection, add each component individually so they may be
          // edited individually.

    for (var i = 0; i < {{ module }}.num_geom; i++) {
        {{ module }}.layers.vector.addFeatures([new OpenLayers.Feature.Vector(admin_geom.geometry.components[i].clone())]);
    }
}else {
     {{ module }}.layers.vector.addFeatures([admin_geom]);
}
    // Zooming to the bounds.
    {{ module }}.map.zoomToExtent(admin_geom.geometry.getBounds());
        if ({{ module }}.is_point){
             {{ module }}.map.zoomTo({{ point_zoom }});

        }
}


// This allows editing of the geographic fields -- the modified WKT is
// written back to the content field (as EWKT, so that the ORM will know
// to transform back to original SRID).

 {{ module }}.layers.vector.on({"featuremodified" : {{ module }}.modify_wkt});
 {{ module }}.layers.vector.on({"featureadded" : {{ module }}.add_wkt});


     {% block controls %}
    // Map controls:
    // Add geometry specific panel of toolbar controls
    {{ module }}.getControls(source);
    // {{ module }}.panel.addControls({{ module }}.controls);
    // {{ module }}.map.addControl({{ module }}.panel);
    // {{ module }}.addSelectControl();

    // Then add optional visual controls
    // {% if mouse_position %}{{ module }}.map.addControl(new OpenLayers.Control.MousePosition());{% endif %}
    // {% if scale_text %}{{ module }}.map.addControl(new OpenLayers.Control.Scale());{% endif %}
    // {% if layerswitcher %}{{ module }}.map.addControl(new OpenLayers.Control.LayerSwitcher());{% endif %}
    // Then add optional behavior controls
    // {% if not scrollable %}{{ module }}.map.getControlsByClass('OpenLayers.Control.Navigation')[0].disableZoomWheel();{% endif %}
    {% endblock %}

       if (wkt){
        if ({{ module }}.modifiable){
            {{ module }}.enableEditing();
        }
    } else {
        {{ module }}.enableDrawing();
    }



// var modify = new ol.interaction.Modify({ source: source });
// {{ module }}.map.addInteraction(modify);

// var draw, snap; // global so we can remove them later
// var typeSelect = document.getElementById('type');


// function addInteractions() {
//     draw = new ol.interaction.Draw({
//         source: source,
//         type: typeSelect.value
//     });
//     {{ module }}.map.addInteraction(draw);
//     snap = new ol.interaction.Snap({ source: source });
//     {{ module }}.map.addInteraction(snap);

// }


/**
 * Handle change event.
 */
// typeSelect.onchange = function () {
//     {{ module }}.map.removeInteraction(draw);
//     {{ module }}.map.removeInteraction(snap);
//     addInteractions();
// };

// addInteractions();



// Read WKT from the text field.
var wkt = document.getElementById('{{ id }}').value;





};

// Baselayer:














