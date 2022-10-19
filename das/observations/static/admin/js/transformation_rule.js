(function ($) {
    'use strict';

    let tranform_rules = $('#id_transforms');
    let message = JSON.parse(tranform_rules.val()) ? JSON.parse(tranform_rules.val()) : []
    let dest_index = {}
    var tempUnit = {};

    let get_dest = function (source) {
        source = source.split('.')
        return source[source.length - 1] === "[]" ? source[source.length - 2] : source[source.length - 1]
    }

    /* map dest value to row index.: */
    let map_dest_index = function () {
        let i;
        dest_index = {}
        for (i = 0; i < message.length; i++) {
            let dest = message[i].dest;
            dest_index[dest] = i;
        }
    }

    map_dest_index();
    let err = $('.errorlist').text()

    err.includes('must be properly configured') ? tranform_rules.show() : tranform_rules.hide();
    tranform_rules.before("<p style=\"color: #777; margin-left: 10px;\">Advanced transformation rules (<span><a class=\"click-toggle\"  href='javascript:'>Show</a></span>) </p>")

    let get_value = function (e) {
        let target = e.target;
        let row = target.id.split('_')[2];
        let value = target.value;
        let source = $(`#transform_key-${row}`).text();
        let destination = get_dest(source);
        let index = dest_index[destination];

        return { index: index, value: value }
    }

    $(document).ready(function () {

        let i;
        let rules = $('[id^="id_transformation_rule_"]')

        for (i = 0; i < rules.length; i++) {
            if (rules[i].checked) {
                $(`#transform_label_${i}`).removeAttr('disabled');
                $(`#transform_unit_${i}`).removeAttr('disabled');
            } else {
                $(`#transform_label_${i}`).attr('disabled', 'disabled');
                $(`#transform_unit_${i}`).attr('disabled', 'disabled');
            }

        }

    })

    $('.click-toggle').click(function (event) {

        let x = event.target;
        if (x.text === "Show") {
            $('#id_transforms').show()
            x.text = "Hide";
        } else if (x.text === "Hide") {
            $('#id_transforms').hide()
            x.text = "Show";
        }

    })

    $('[id^="id_transformation_rule_"]').change(function (event) {
        let checkbox = event.target;
        let row = checkbox.id.split('_')[3];
        let source = $(`#transform_key-${row}`).text()
        let destination = get_dest(source)
        let index = dest_index[destination]

        if (index === undefined) {
            $(`#transform_unit_${row}`).val(tempUnit[source]);
            source = source.replaceAll('[]', "[0]")
            message.push({
                "default": tempUnit[source + '_default'],
                "dest": `${destination}`,
                "label": `${destination}`,
                "source": `${source}`,
                "units": tempUnit[source]
            })
            let new_msg = JSON.stringify(message, undefined, 2);
            $('#id_transforms').val(new_msg);
            map_dest_index()
        }

        if (checkbox.checked) {
            let label_el = $(`#transform_label_${row}`)
            let defaultElement = $(`#transform_unit_${row}`).parent().parent().find("[name='default']");
            label_el.removeAttr('disabled');
            $(`#transform_unit_${row}`).removeAttr('disabled');
            label_el.val(destination)
            defaultElement.prop("disabled", false);
            defaultElement.prop("checked", tempUnit[destination + '_default']);

        } else {
            let label_element = $(`#transform_label_${row}`);
            let unit_element = $(`#transform_unit_${row}`);
            let defaultElement = $(`#transform_unit_${row}`).parent().parent().find("[name='default']");
            tempUnit[$(`#id_transformation_rule_${row}`).val()] = document.getElementById(`transform_unit_${row}`).value;
            tempUnit[$(`#id_transformation_rule_${row}`).val() + '_default'] = defaultElement.is(':checked');

            label_element.attr('disabled', 'disabled');
            unit_element.attr('disabled', 'disabled');
            defaultElement.prop("checked", false);
            defaultElement.prop("disabled", true);

            /* update value */
            label_element.val('');
            unit_element.val('');

            message.splice(index, 1);
            let new_msg = JSON.stringify(message, undefined, 2);
            $('#id_transforms').val(new_msg);
            map_dest_index()
        }
    })

    $('[id^="transform_label_"]').keyup(function (event) {
        let index_value = get_value(event);
        let index = index_value.index;

        message[index].label = index_value.value;
        let msg = JSON.stringify(message, undefined, 2);
        $('#id_transforms').val(msg);
    });

    $('[id^="transform_unit_"]').keyup(function (event) {
        let index_value = get_value(event);
        let index = index_value.index;

        message[index].units = index_value.value;
        let msg = JSON.stringify(message, undefined, 2);
        $('#id_transforms').val(msg);
    })

    $('input[type=radio][name=default]').change(function (event) {
        message.forEach(element => {
            element.default = element.dest === this.value;
        });
        let msg = JSON.stringify(message, undefined, 2);
        $('#id_transforms').val(msg);
    });

})(django.jQuery);
