{% extends "gis/admin/osm.js" %}


{% block controls %}
{{ block.super }}
{{ module }}.map.addControl(new OpenLayers.Control.Navigation().activate());


{% endblock %}


