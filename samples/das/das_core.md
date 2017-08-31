# DAS Data Model

This sample contains the DAS data model. It is meant to be loaded for a new site.

## Files
### accounts.json
### mappings.json



## dumpdata commands
    python manage.py dumpdata activity.eventtype activity.eventcategory --format json -o eventtype.json --indent 2 --natural-foreign
    python manage.py dumpdata accounts.permissionset --format json -o activity_permissionset.json --indent 2 --natural-foreign
    python manage.py dumpdata choices.choice choices.dynamicchoice --format json -o choices.json --indent 2 --natural-foreign
    python manage.py dumpdata activity.eventclass activity.eventfactor activity.eventclassfactor --format json -o eventmatrix.json --indent 2 --natural-foreign
    python manage.py dumpdata mapping.map --format json -o maps.json --indent 2 --natural-foreign

## loaddata commands


 