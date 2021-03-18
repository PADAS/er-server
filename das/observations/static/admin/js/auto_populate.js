(function ($) {
    'use strict';

    let tranform_rules = $('#id_transforms')
    let message = JSON.parse(tranform_rules.val()) ? JSON.parse(tranform_rules.val()) : []
    let index_value = {}


    /* map source value to row index.: */
    let map_source_index = function () {
        let i;
        index_value = {}
        for (i = 0; i < message.length; i++) {
            let source = message[i].source;

            index_value[source] = i;
        }
    }

    map_source_index();
    tranform_rules.hide();
    tranform_rules.before("<p style=\"color: #777; margin-left: 10px;\">Advanced transformation rules (<span><a class=\"click-toggle\"  href='javascript:'>Show</a></span>) </p>")

    let get_value = function (e) {
        let target = e.target
        let row = target.id.split('_')[2];
        let value = target.value;
        let source = $(`#transform_key-${row}`).text()
        let index = index_value[source];

        return {index: index, value: value}
    }

    $(document).ready(function () {
        console.log("login")
        let i;
        let rules = $('[id^="id_tranformation_rule_"]')

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


    $('[id^="id_tranformation_rule_"]').change(function (event) {
        let checkbox = event.target;
        let row = checkbox.id.split('_')[3];
        let source = $(`#transform_key-${row}`).text()
        let dest = source.split('.')
        let index = index_value[source]

        if (index === undefined) {
            // console.log(message)
            let destination = dest[dest.length - 1] === "[]" ? dest[dest.length - 2] : dest[dest.length - 1]
            message.push({"dest": `${destination}`, "label": "", "source": `${source}`, "units": ""})
            let new_msg = JSON.stringify(message, undefined, 2);
            $('#id_transforms').val(new_msg);
        }
        map_source_index()

        if (checkbox.checked) {
            $(`#transform_label_${row}`).removeAttr('disabled');
            $(`#transform_unit_${row}`).removeAttr('disabled');

        } else {
            let label_element = $(`#transform_label_${row}`);
            let unit_element = $(`#transform_unit_${row}`);

            label_element.attr('disabled', 'disabled');
            unit_element.attr('disabled', 'disabled');

            /* update value */
            label_element.val('');
            unit_element.val('');

            message.splice(index, 1);
            let new_msg = JSON.stringify(message, undefined, 2);
            $('#id_transforms').val(new_msg);
            map_source_index()
        }

    })

    $('[id^="transform_label_"]').keyup(function (event) {
        let index_value = get_value(event);
        let index = index_value.index;

        message[index].label = index_value.value;
        let msg = JSON.stringify(message, undefined, 2);
        $('#id_transforms').val(msg);
    })


    $('[id^="transform_unit_"]').keyup(function (event) {
        let index_value = get_value(event);
        let index = index_value.index;

        message[index].units = index_value.value;
        let msg = JSON.stringify(message, undefined, 2);
        $('#id_transforms').val(msg);
    })


})(django.jQuery);

