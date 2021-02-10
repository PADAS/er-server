(function($) {
    $(function() {
        var new_device_config = $('#id_new_device_config'), verified = $('.new_subject_types');
        var name_change_config = $('#id_name_change_config'), verified2 = $('.name_change_types');

        var new_device_match_case = $('.fieldBox.field-new_device_match_case');
        var name_change_match_case = $('.fieldBox.field-name_change_match_case');

        function toggleVerified(value) {
            console.log(value[0].name)

            types_class = (value[0].name == 'new_device_config') ? verified : verified2
            match_case_class = (value[0].name == 'new_device_config') ? new_device_match_case : name_change_match_case

            if (value.val() === 'use_existing') {
                types_class.show();
                match_case_class.show()
            } else {
                types_class.hide();
                match_case_class.hide()
            }
        }

        var mylist = [new_device_config, name_change_config];
        for (var i = 0; i < mylist.length; i++) {
            field = mylist[i]
            toggleVerified(field);
            field.change(function() {
                toggleVerified($(this));
            });
            }
    });
})(jQuery);
