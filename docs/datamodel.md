# DAS Report Data Model
## DAS JSON SCHEMA reference list
~~~~
{
  "schema":
  {
      "$schema": "http://json-schema.org/draft-04/schema#",
      "title": "DAS JSON Schema Reference List",
   
      "type": "object",

      "properties":
      {
           "string_field": {
               "type": "string",
               "title": "This is the Title Of the Field"
           },
           "number_field": {
               "type": "number",
               "title": "This is a number field with values between 0 and 360",
               "minimum": 0,
               "maximum": 360
           },
           "time_field": {
               "type": "string",
               "title": "This is a time field.  Look below in Definition section to get date-time-picer"
           },
           "table_field": {
               "type": "string",
               "title": "This is a drop down list populated from a Table",
               "enum": {{table___TrafficType___values}},
               "enumNames": {{table___TrafficType___names}}                
           },
           "enum_field": {
               "type": "string",
               "title": "This is a drop down list populated from the generic table named Choices",
               "enum": {{enum___yesno___values}},
               "enumNames": {{enum___yesno___names}}                
           },
           "query_field": {
               "type": "string",
               "title": "This is a drop down list populated from a query in Dynamic Choices table",
                 "enum": {{query___whiteRhinos___values}},
                "enumNames": {{query___whiteRhinos___names}}                
           },
           "multi_select_field": {
              "key": "sectionArea"
           }
      }
  },
"definition": [
  "string_field",
  "number_field",
  {
  "key": "time_field",
  "fieldHtmlClass": "date-time-picker json-schema",
  "readonly": false
  },
  "table_field",
  "enum_field",
  "query_field",
  {
            "key": "sectionArea",
            "type": "checkboxes",
            "title": "Planned Patrol Areas",
            "titleMap": {{table___sectionArea___map}},
            "htmlClass": "json-schema-checkbox-wrapper"    
  }  
]
}
~~~~

## example schema
~~~~
{
   "schema": 
   {
       "$schema": "http://json-schema.org/draft-04/schema#",
       "title": "DET REP Report (shot_rep)",
     
       "type": "object",

       "properties": 
       {
            "shotrep_location": {
                "type": "string",
                "title": "Line 1: UTM grid reference of your location at time of detection"
            },            
            "shotrep_timeofshot": {
                "type": "string",
                "title": "Line 2: Time when shot was heard"
            },
            "shotrep_whatdetected": {
                "type": "string",
                "title": "Line 3: What was detected"
            },            
            "shotrep_bearing": {
                "type": "number",
                "title": "Line 4: Bearing to Shot",
                "minimum": 0,
                "maximum":  360
            },                      
            "shotrep_distance": {
                "type": "number",
                "title": "Line 5: Distance of Shots (m)",
                "minimum": 0
            },                      
            "shotrep_numberofshots": {
                "type": "number",
                "title": "Line 6.1: Number of Shots",
                "minimum": 0
            },
            "shotrep_typeofshots": {
                "type": "string",
                "title": "Line 6.2. Rate of Fire",
                "enum": {{enum___shotrep_typeofshot___values}},
                "enumNames": {{enum___shotrep_typeofshot___names}}                  
            },              
            "shotrep_estimatedcaliber": {
                "type": "string",
                "title": "Line 6.3: Estimated Caliber",
                "enum": {{enum___shotrep_estimatedcaliber___values}},
                "enumNames": {{enum___shotrep_estimatedcaliber___names}}                  
            },
            "shotrep_patrolresponse": {
                "type": "string",
                "title": "Line 7: Patrols Response/Intent"
            }
       }
   },
 "definition": [
    {
        "key":   "shotrep_location",
        "htmlClass": "col-lg-6"
    }, 
    {
        "key": "shotrep_timeofshot",
        "fieldHtmlClass": "date-time-picker json-schema",
        "readonly": false,
        "htmlClass": "col-lg-6"   
    },
    {
       "key":    "shotrep_whatdetected",
        "htmlClass": "col-lg-6"
    }, 
    {
       "key":    "shotrep_bearing",
        "htmlClass": "col-lg-6"
    }, 
    {
       "key":    "shotrep_distance",
        "htmlClass": "col-lg-6"
    }, 
    {
       "key":    "shotrep_numberofshots",
        "htmlClass": "col-lg-6"
    }, 
    {
       "key":    "shotrep_typeofshots",
        "htmlClass": "col-lg-6"
    }, 
    {
       "key":    "shotrep_estimatedcaliber",
        "htmlClass": "col-lg-6"
    }, 
    {
       "key":    "shotrep_patrolresponse"
        "htmlClass": "col-lg-6"
    }     
 ]
}
~~~~

## Adding multiple columns
~~~~
REGEX to add two column support in DAS json schema

Find whole line
^(    "[^"]*",)


Replace     

    {
        "key": $1
        "htmlClass": "col-lg-6"
    }, 
~~~~

## Event Types management command

### manageevent
django command name for managing DAS event types
~~~
python manage.py manageevent dumptypes -o eventtypes.json
~~~

#### dumptypes
sub command to export all event types including what enum, query and table references are made in the event type schema
	
-o file to output json data
Result is a list of event type objects
~~~	
	{
		id
		value
		display
		category_value
		category_id
		ordernum
		schema
		is_collection
		count - number of events using this type
		
		tables [] - table references in schema
		{
			table_name
		}
		enums [] - enum references in schema
		queries [] - query references in schema
		fields[]  - the fields found in the schema field for reference
		{
			property_name
		}
	}
~~~~
	
#### deleteunusedtypes
delete the event types that are not referenced in the current list of events.
	
--dry-run - output the types that will be deleted, but not actually delete them
	
#### migratetypes
Migrate the current set of event types. Takes a file of updated and new types as input.
The input format is expected to be the same as that from the dumptypes command above. Additionally, an event type object can define how to merge an existing type with the one contained in the file and how to migrate choices tables data into choices.choice.

A choice entry is referenced by a combination of the table or enum name found in the event type schema for that data field and a UUID for the specific record as stored in the eventdetails data.
Enum and Query records do not require updating, Table records must be migrated.
~~~
field: station
enum: table___station___values
stored value in data:
    single entry: "station": "7ce5a616-ec7b-4d4f-b637-f7ed86740d6a"
    multiple choice: "station": [{"name": "Buhira  (Section 3)", "value": "7ce5a616-ec7b-4d4f-b637-f7ed86740d6a"}, {"name": "Lake Gishanju  (Section 3)", "value": "e1989de4-3400-482a-8b42-0d0ec16c8d94"}]
~~~

-f file containing the new set of event types

By annotating the table[] objects, instructs migration to include migrating choices table data into the single choice data. This will not overwrite existing data in the choice table when performing a lookup by id(uuid).

The fields[] list is there to describe field name changes in the schema. This requires visiting all eventdetails for that event type and change the field name in the data. For example, changing "

Additional meta data for controlling merge and migration:
~~~
{
    tables[]
    {
        table_name - name of existing choices table, rows are migrated from here into the choice table
        field - by including a field name, migrate choices table to choice table using field and model
        model - optional, default is 'activity.event'
    }
    fields[]
    {
        property_name - field name in the json schema for this event type
        previous_property_name - when specified, update existing eventdetail data with this name to the new property_name
        
    }
} 
~~~