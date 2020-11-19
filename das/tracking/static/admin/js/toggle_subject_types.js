(function($) {
    $(function() {
        var new_device_config = $('#id_new_device_config'), verified = $('.new_subject_types');
        var name_change_config = $('#id_name_change_config'), verified2 = $('.name_change_types');

        function toggleVerified(value) {
            console.log(value[0].name)

            types_class = (value[0].name == 'new_device_config') ? verified : verified2

            if (value.val() === 'use_existing') {
                types_class.show();
            } else {
                types_class.hide();
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
