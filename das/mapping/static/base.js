(function($) {
    $(function() {
        var selectFileType = $('#id_file_type'), readonlyFields = document.getElementsByClassName("readonly"),
            ste = $('.ste'), shapefile= $('.shapefile');

        if(readonlyFields.length > 1){
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
            if (value === 'shapefile') {
                shapefile.show();
                ste.hide();
            } else if(value === 'ste') {
                shapefile.hide();
                ste.show();
            }
        }
    });
})(django.jQuery);
