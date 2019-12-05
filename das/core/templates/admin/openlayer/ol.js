
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
{{ module }}.tile_layers = {{ tile_layers|safe }};

{% endblock %}


{{ module }}.init = function() {
    {% block map_options %} // The options hash, w/ zoom, resolution, and projection settings.
    var options = {
        {% autoescape off %}
        {% for item in map_options.items %}
        '{{ item.0 }}' : {{ item.1 }},
        {% endfor %}{% endautoescape %}
    };
{% endblock %}


{{ module }}.get_ewkt = function(feat){
    return 'SRID={{ srid|unlocalize }};' + {{ module }}.wkt_f.writeFeature(feat);
};

var write_wkt = function(feat) {
    document.getElementById('{{ id }}').value = {{ module }}.get_ewkt(feat);
};

var add_wkt = function (event){
    /**
    * This Function will sync content of vector layer with WKT in the text field
    */
   if ({{ module }}.is_collection){

       var feat = source.getFeatures();
       var eventCoord =  event.feature.getGeometry().getCoordinates();
       var coordinates = [];
       var type;
       feat.forEach( function(feat){
           var coord = feat.getGeometry().getCoordinates();
           type = feat.getGeometry().getType();
           if (type == '{{ geom_type }}') {
               for (i = 0; i < coord.length; i++) {
                   coordinates.push(coord[i]);
                }} else {
                    coordinates.push(coord)
                };
            });
            var feats = new ol.Feature({
                geometry: new ol.geom.{{ geom_type}}(coordinates)
            });
            write_wkt(feats)
        }else {
            if (source.getFeatures().length > 1) {
                old_feats = source.getFeatures()[0];
                source.removeFeature(old_feats);
            }
            write_wkt(event.feature);
        };
    };

var modify_wkt = function(event) {
    /*
    * Modift WKT-Textfied
    * Modify the selected component: vector-layer
    */
   if ({{ module }}.is_collection){

    var feat = source.getFeatures();
    var eventCoord =  event.feature.getGeometry().getCoordinates();
    var coordinates = [];
    var type;
    feat.forEach( function(feat){
        var coord = feat.getGeometry().getCoordinates();
        type = feat.getGeometry().getType();
        if (type == '{{ geom_type }}') {
            for (i = 0; i < coord.length; i++) {
                coordinates.push(coord[i]);
            }} else {
                coordinates.push(coord)
            };
        });var feats = new ol.Feature({
            geometry: new ol.geom.{{ geom_type}}(coordinates)
        });
        write_wkt(feats)
    }else {
        write_wkt(event.feature);
    };
};


{{ module }}.showHideWKT = function (){
    var aTag = document.querySelector('.click-toggle');
    if (aTag.innerHTML == 'Show'){
        textArea = document.getElementById("{{ id }}")
        textArea.style.display = 'block';
        aTag.innerHTML = 'Hide'
    } else if  (aTag.innerHTML == 'Hide'){
        textArea = document.getElementById("{{ id }}")
        textArea.style.display = 'none';
        aTag.innerHTML = 'Show'
    }
};




var CreateTileLayer = function(){
    TileLayers = {{ module }}.tile_layers;
    var array = [];
    TileLayers.forEach(function(tile){

        var tile_link = tile.attributes.url;
        var TileLayer = new ol.layer.Tile({
            source: new ol.source.XYZ({
                url: tile_link
            })

        });
        object = {};
        var id = tile.attributes.title.replace(/\s/g, "").toLowerCase() + '_id';
        object[id] = TileLayer;
        array.push(object);
    });
    return array

};


var raster = new ol.layer.Tile({
    source: new ol.source.OSM()
});

// var google_hybrid_url = 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}';

// var google_satellite_layer = new ol.layer.Tile({
//     source: new ol.source.XYZ({
//         url: google_hybrid_url + '&client=AIzaSyArYgAAi9immeQFbEO2_6dRgc7hCSLaOIo'
//     })
// });

var source = new ol.source.Vector({
    format: new ol.format.GeoJSON()
});
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
            radius: 8,
            fill: new ol.style.Fill({
                color: '#65cdcc'
            })
        })
    })
});


var map = new ol.Map({
    view: new ol.View({
        center: ol.proj.transform([{{default_lon}}, {{default_lat}}], 'EPSG:4326', 'EPSG:4326'),
        maxResolution: options.maxResolution,
        zoom: options.numZoomLevels,

        projection: options.projection.projection_,
        extend: options.maxExtent,
    }),
    layers: [raster, vector],
    target: '{{ id }}_map',
    controls: new ol.control.defaults().extend([
        new ol.control.FullScreen()

    ])
});



var mousewheel = new ol.interaction.MouseWheelZoom()
map.addInteraction(mousewheel);

map.on('moveend', (event) => {
    var newZoom = map.getView().getZoom();
    sessionStorage.setItem("zoomLevel", newZoom);
});


// var zoom = sessionStorage.getItem("zoomLevel");
// // if zoom was saved in sessionstorage, then use it to zoom the map else default to numZoomLevels
// if (zoom !== null) {
//     map.getView().setZoom(zoom);
// } else {
//     zoom = options.numZoomLevels
// }


// Geometric Object
var createGeometricObject = function(innerHTML, geoType, className){
    var button = document.createElement('button');
    button.innerHTML = innerHTML;

    var type = "{{ geom_type }}";
    var geometricObject = function(e){
        e.preventDefault()
        map.getInteractions().pop();

        var el = document.getElementById("card");
        if (el.style.display === "grid") {
            el.style.display = "none";
        };

        draw = new ol.interaction.Draw({
            source: source,
            type: geoType
        });
        if (!type){
            draw.on('drawend', function (event) {
                map.removeInteraction(draw);
            });
        };
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
if ("{{ geom_type }}" == "MultiPolygon" || {{ module }}.is_polygon == true) {
    var polygonUrl = '<img class="img_1" src="https://img.icons8.com/ios-glyphs/30/ffffff/polygon.png">';
    createGeometricObject(polygonUrl, 'Polygon', 'ol-point');
} else if ("{{ geom_type }}" != "MultiLineString" && "{{ geom_type }}" != "MultiPoint" && {{ module }}.is_linestring != true) {
    var polygonUrl = '<img class="img_1" src="https://img.icons8.com/ios-glyphs/30/ffffff/polygon.png">';
    createGeometricObject(polygonUrl, 'Polygon', 'ol-polygon');
};

// Linestring
if ("{{ geom_type }}" == "MultiLineString" || {{ module }}.is_linestring == true){
    var linestringUrl = '<img class="img_1" src="https://img.icons8.com/ios-filled/50/ffffff/polyline.png">';
    createGeometricObject(linestringUrl, 'LineString', 'ol-point');
} else if ("{{ geom_type }}" != "MultiPolygon" && "{{ geom_type }}" != "MultiPoint" && {{ module }}.is_polygon != true && {{ module }}.is_point != true){
    var linestringUrl = '<img class="img_1" src="https://img.icons8.com/ios-filled/50/ffffff/polyline.png">';
    createGeometricObject(linestringUrl, 'LineString', 'ol-linestring');
};

// Point
if ("{{ geom_type }}" == "MultiPoint" || "{{ geom_type }}" != "MultiPolygon" && "{{ geom_type }}" != "MultiLineString" && {{ module }}.is_polygon != true && {{ module }}.is_linestring != true ) {
    var pointUrl = '<img class="img_2" src="https://img.icons8.com/material-rounded/24/ffffff/filled-circle.png">';
    createGeometricObject(pointUrl, 'Point', 'ol-point');
};

// Modify
var modif = function(className) {
    var button_modify = document.createElement('button');
    button_modify.innerHTML = '<img class="img_1" src="https://img.icons8.com/ios-glyphs/24/ffffff/map-editing--v2.png">';

    var modify = function (e) {
        e.preventDefault();
        modify = new ol.interaction.Modify({ source: source });
        map.getInteractions().pop()

        var el = document.getElementById("card");
        if (el.style.display === "grid") {
            el.style.display = "none";
        };

        map.addInteraction(modify);
    };

    button_modify.addEventListener('click', modify, false);

    var element_modify = document.createElement('div');
    element_modify.className =  `${className} ol-unselectable ol-control`;
    element_modify.appendChild(button_modify);

    var modifyControl = new ol.control.Control({
        element: element_modify
    });
    map.addControl(modifyControl);
};


// Delete
var delet = function (className){
    var button_delete = document.createElement('button');
    button_delete.innerHTML = '<img class="img_1" src="https://img.icons8.com/ios-filled/24/ffffff/delete-sign.png">';

    var deleteFeatures = function (e) {
        e.preventDefault();
        result = confirm("Want to clear all features?");
        if (result){
            source.clear();
            document.getElementById('{{ id }}').value = '';
        }
    };

    button_delete.addEventListener('click', deleteFeatures, false);

    var element_delete = document.createElement('div');
    element_delete.className = `${className} ol-unselectable ol-control`;
    element_delete.appendChild(button_delete);

    var deleteControl = new ol.control.Control({
        element: element_delete
    });
    map.addControl(deleteControl);
};


if ("{{ geom_type }}" == "MultiPolygon" || "{{ geom_type }}" == "MultiPoint" || "{{ geom_type }}" == "MultiLineString" || {{ module }}.is_polygon == true || {{ module }}.is_linestring == true || {{ module }}.is_point == true ){
    delet('ol-linestring')
} else if ("{{ geom_type }}" != "MultiPolygon" && "{{ geom_type }}" != "MultiPoint") {
    delet('ol-x')
};

if ("{{ geom_type }}" == "MultiPolygon" || "{{ geom_type }}" == "MultiPoint" || "{{ geom_type }}" == "MultiLineString" || {{ module }}.is_polygon == true || {{ module }}.is_linestring == true || {{ module }}.is_point == true) {
    modif('ol-polygon')
} else if ("{{ geom_type }}" != "MultiPolygon" && "{{ geom_type }}" != "MultiPoint") {
    modif('ol-modify')
};

// map.on('pointermove', function(e) {
//     if (e.dragging) return;
//     var pixel = map.getEventPixel(e.originalEvent)
//     var hit = map.hasFeatureAtPixel(pixel);
//     console.log(hit)
//     map.getTargetElement().style.cursor = hit ? 'pointer': '';
// });


var button_baselayer = document.createElement('button');
button_baselayer.innerHTML = '<img class="img_1" id="bl" src="https://img.icons8.com/ios-glyphs/30/ffffff/layers.png">';

var switchBaseLayer = function (e) {
    e.preventDefault();
    try{
    map.getInteractions().pop();
    map.addInteraction(mousewheel);

    }catch(err){
        location.reload();
    }

    var el = document.getElementById("card");
    // console.log(el)
    if (el.style.display === "grid"){
        el.style.display = "none";
    }else{
        el.style.display = "grid";
    }
};

button_baselayer.addEventListener('click', switchBaseLayer, false);

var element_baselayer = document.createElement('div');
element_baselayer.className = 'ol-bl ol-unselectable ol-control';
element_baselayer.appendChild(button_baselayer);

var BaseLayerControl = new ol.control.Control({
    element: element_baselayer
});
map.addControl(BaseLayerControl);


var cardHTML = `<div class="card ol-unselectable ol-control ol-bl" id="card"></div>`;

var olLayersViewPort = document.getElementById('{{ id }}_map').getElementsByClassName("ol-viewport")[0];

olLayersViewPort.insertAdjacentHTML('beforeend', cardHTML);


var TileLayerHTML = function(id, icon_url, name, title){
    var HTML;
    var cardDiv;
    var style = "width: 50%; outline: none;";
    HTML = `<div class="item">
                <input type="image" src="${icon_url}" name="${name}" class="input" id="${id}" style="${style}"/>
                <span> <center>${title}</center> </span>
            </div>`;
    cardDiv = document.getElementById('card');
    cardDiv.insertAdjacentHTML('beforeend', HTML);
};


var swithBaseMapLayer = function(layer){
    map.getLayers().removeAt(0)
    map.getLayers().insertAt(0, layer);
};

var eventListener = function(id){
    document.getElementById(id).addEventListener('click', function (event) {
        event.preventDefault();

        var layers = CreateTileLayer();
        layers.forEach(function(layer){
            if( Object.keys(layer)[0] == id){
                layer = Object.values(layer)[0];
                swithBaseMapLayer(layer)
            }
        })

    });
};

var defaultIcon = "https://img.icons8.com/cotton/256/000000/globe.png";

{{ module }}.tile_layers.forEach( function(layer){
    if (layer.attributes.type == "tile_server"){
        var id = layer.attributes.title.replace(/\s/g, "").toLowerCase()+'_id';
        var name = layer.attributes.title.toLowerCase();
        var title = layer.attributes.title;
        var icon_url = layer.attributes.icon_url;
        if( icon_url != undefined){
            icon_url = icon_url;
        }else{
            icon_url = defaultIcon;
        }
        TileLayerHTML(id, icon_url, name, title);
        eventListener(id);
    };

});




var zoomslider = new ol.control.ZoomSlider();
map.addControl(zoomslider);

var scaleline = new ol.control.ScaleLine();
map.addControl(scaleline);

var dragrotate = new ol.interaction.DragRotateAndZoom()
map.addInteraction(dragrotate);


/**
 * Handle change event.
 */

vector.getSource().on("addfeature", add_wkt)
vector.getSource().on("changefeature", modify_wkt)

var wkt = document.getElementById("{{ id }}").value;

if(wkt) {
    /**
    * Reading feature from TextArea: in WKT format.
    * Draw a feature.
    * var match = {{ module }}.re.exec(wkt);
    */
    admin_geom = {{ module }}.wkt_f.readFeature(wkt);

    write_wkt(admin_geom);
    source.addFeatures([admin_geom]);

    // Zooming to the bounds
    // extent = map.getView().calculateExtent();
    var extent = source.getExtent();

    map.getView().fit(extent, map.getSize());

    if (source.getFeatures()[0].getGeometry().getType() == 'Point' || '{{ geom_type }}' == 'MultiPoint'){
        map.getView().setZoom(map.getView().getZoom()-8);
    }
}};



