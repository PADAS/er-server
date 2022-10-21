(function($) {
    $(function() {
        var selectFileType = $('#id_file_type'), readonlyFields = document.getElementsByClassName("readonly"),
        geojson = $('.geojson'), shapefile= $('.shapefile');

        if(readonlyFields.length > 2){
            toggleVerified(readonlyFields[0].innerHTML.toLowerCase());
        }
        else{
            // show/hide on load based on pervious value of selectField
            toggleVerified(selectFileType.val());

            // show/hide fieldset on change of file type
            selectFileType.change(function() {
                toggleVerified($(this).val());
            });
        }

        function toggleVerified(value) {
            if (value === 'shapefile' || value === 'geodatabase') {
                shapefile.show();
                geojson.hide();
            } else if(value === 'geojson') {
                shapefile.hide();
                geojson.show();
            }
        }
    });
})(django.jQuery);
