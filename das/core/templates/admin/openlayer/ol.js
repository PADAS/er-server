
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

    // source.clear()
    // document.getElementById('{{ id }}').value = '';
    // {% localize off %}
    // map.getView().setCenter(ol.proj.transform([{{ default_lon}}, {{ default_lat}}], 'EPSG:4326', 'EPSG:3857'));
    // map.getView().setZoom({{ default_zoom }});
    // {% endlocalize %}

var raster = new ol.layer.Tile({
    source: new ol.source.OSM()
});
var rasterEsriTop = new ol.layer.Tile({
    source: new ol.source.XYZ({
        url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
        attributions: 'Tiles © <a href="https://services.arcgisonline.com/ArcGIS/' +'rest/services/World_Topo_Map/MapServer">ArcGIS</a>',
    })
});

var rasterEsriSAT = new ol.layer.Tile({
    source: new ol.source.XYZ({
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attributions: 'Tiles © <a href="https://services.arcgisonline.com/ArcGIS/' + 'rest/services/World_Imagery/MapServer">ArcGIS</a>',

    })
});

var rasterNGS= new ol.layer.Tile({
    source: new ol.source.XYZ({
        url: 'https://services.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}'
    })
});
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
    layers: [raster, rasterEsriSAT, rasterEsriTop, rasterNGS, vector],
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


var zoom = sessionStorage.getItem("zoomLevel");
// if zoom was saved in sessionstorage, then use it to zoom the map else default to numZoomLevels
if (zoom !== null) {
    map.getView().setZoom(zoom);
} else {
    zoom = options.numZoomLevels
}


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

var disableRaster = function(){
    rasterEsriSAT.setVisible(false)
    rasterEsriTop.setVisible(false)
    rasterNGS.setVisible(false)
};
disableRaster()


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

var esriControlsHtml = `<div class="card ol-unselectable ol-control ol-bl" id="card">
            <div class="item">
                <input type="image" src="https://d1iq7pbacwn5rb.cloudfront.net/opendata-ui/assets/assets/images/esri-logo-color-6c1dbc86c0f28b9278d38cdf5c768e72.png" name="esri-tp" class="input" id="esri_tp"/>
                <span> <center> ESRI Topography</center> </span>
            </div>
            <div class="item">
                <input type="image"
                    src="https://d1iq7pbacwn5rb.cloudfront.net/opendata-ui/assets/assets/images/esri-logo-color-6c1dbc86c0f28b9278d38cdf5c768e72.png"
                    name="esri-stl" class="input" id="esri_stl" />
                <span>
                    <center> ESRI Satellite</center>
                </span>
            </div>
            <div class="item">
                <input type="image"
                    src="https://img.icons8.com/cotton/256/000000/globe.png"
                    name="ngs" class="input" id="ngs_" />
                <span>
                    <center> NGS</center>
                </span>
            </div>
            <div class="item">

                <input type="image" src="https://upload.wikimedia.org/wikipedia/commons/thumb/b/b0/Openstreetmap_logo.svg/1200px-Openstreetmap_logo.svg.png" name="osm" class="input" id="osm_" />
                <span>
                    <center> OpenStreet Map</center>
                </span>
            </div>
        </div>`;

var olLayersViewPort = document.getElementById('{{ id }}_map').getElementsByClassName("ol-viewport")[0]

olLayersViewPort.insertAdjacentHTML('beforeend', esriControlsHtml);


document.getElementById('esri_tp').addEventListener('click', function(e){
    e.preventDefault();
    disableRaster();
    raster.setVisible(false);
    rasterEsriTop.setVisible(true);
});


document.getElementById('esri_stl').addEventListener('click', function (e) {
    e.preventDefault();
    disableRaster();
    raster.setVisible(false);
    rasterEsriSAT.setVisible(true);
});

document.getElementById('ngs_').addEventListener('click', function (e) {
    e.preventDefault();
    disableRaster();
    raster.setVisible(false);
    rasterNGS.setVisible(true);
});

document.getElementById('osm_').addEventListener('click', function (e) {
    e.preventDefault();
    disableRaster();
    raster.setVisible(true);
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



