(function($) {
    $(function() {
        var selectField = $('#id_new_subject_config'),
            verified = $('.new_subject_types');

        function toggleVerified(value) {
            if (value === 'use_existing') {
                verified.show();
            } else {
                verified.hide();
            }
        }

        // show/hide on load based on pervious value of selectField
        toggleVerified(selectField.val());

        console.log(selectField.val())

        // show/hide on change
        selectField.change(function() {
            toggleVerified($(this).val());
        });
    });
})(django.jQuery);