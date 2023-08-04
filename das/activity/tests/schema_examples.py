ET_SCHEMA = """{
    "schema":
    {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Locust Hoppers Report (locusthoppers_rep)",
        "type": "object",
        "properties":
        {
        "repObserver": {
            "type": "string",
            "title": "Report Observer"
        },
        "repHASurveyed": {
            "type": "number",
            "title": "HA Surveyed",
            "minimum": 0
        },
        "livestock_killed_array":{
            "title": "Livestock Killed",
            "type": "array",
            "items":
            {
                "type":"object",
                "properties":{
                "Animal Name":{
                "title":"Type of Livestock/ Poultry",
                "type":"string",
                "enum": {{enum___behavior___values}},
                "enumNames": {{enum___behavior___names}}
                },
                "Number":{
                "title":"No. of Animals",
                "type":"number",
                "minimum":1}
                }
            }
          },
        "repCountry": {
            "type": "string",
            "title": "Country",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "repLocation": {
            "type": "string",
            "title": "Report Location"
        },
        "HopActivitySelect": {
            "key": "HopActivitySelect"
        },
        "HopAppearance": {
            "type": "string",
            "title": "Appearance",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "HopAvgTuftDistance": {
            "type": "number",
            "title": "Average distance between tufts"
        },
        "HopBehaviour": {
            "type": "string",
            "title": "Behaviour",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "HopColourSelect": {
            "key": "HopColourSelect"
        },
        "HopDensity": {
            "type": "string",
            "title": "Density",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "HopDensityAvg": {
            "type": "number",
            "title": "Density average"
        },
        "HopDensityMax": {
            "type": "number",
            "title": "Density maximum"
        },
        "HopDensityMin": {
            "type": "number",
            "title": "Density minimum"
        },
        "HopDensityUnit": {
            "type": "string",
            "title": "Density unit",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "HopStageSelect": {
            "key": "HopStageSelect"
        },
        "HopStageDom": {
            "type": "string",
            "title": "Dominant",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "HopActivity": {
            "type": "string",
            "title": "Activity",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "HopStage": {
            "type": "string",
            "title": "Stage",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "HopColour": {
            "type": "string",
            "title": "Colour",
            "enum": {{enum___behavior___values}},
            "enumNames": {{enum___behavior___names}}
        },
        "eLocust-key": {
            "type": "string",
            "title": "e-locust-key"
        }
    }
},
  "definition": [
    {
      "type": "fieldset",
      "title": "Report Info",
      "htmlClass": "col-lg-12",
      "items": []
    },
    {
      "type": "fieldset",
      "htmlClass": "col-lg-6",
      "items": [
        "repObserver",
        "repHASurveyed"
      ]
    },
    {
      "type": "fieldset",
      "htmlClass": "col-lg-6",
      "items": [
        "repCountry",
        "repLocation"
      ]
    },
    {
      "type": "fieldset",
      "title": "Hoppers Info",
      "htmlClass": "col-lg-12",
      "items": []
    },
    {
      "type": "fieldset",
      "htmlClass": "col-lg-6",
      "items": [
        { "key": "HopStageSelect", "type": "checkboxes", "title": "Stage", "titleMap": {{enum___behavior___map}}},
        "HopStageDom",
        "HopAppearance",
        "HopBehaviour",
        { "key": "HopColourSelect", "type": "checkboxes", "title": "Colour", "titleMap": {{enum___behavior___map}}}
      ]
    },
    {
      "type": "fieldset",
      "htmlClass": "col-lg-6",
      "items": [
        "HopDensityUnit",
        "HopDensity",
        "HopDensityMin",
        "HopDensityAvg",
        "HopDensityMax",
        "HopAvgTuftDistance",
        { "key": "HopActivitySelect", "type": "checkboxes", "title": "Activity", "titleMap": {{enum___animalcontrolrep_species___map}}}
      ]
    }
  ]
}"""

WILDLIFE_SCHEMA = """
{
   "schema":
   {
       "$schema": "http://json-schema.org/draft-04/schema#",
       "title": "Other Wildlife Sighting Report (wildlife_sighting_rep)",

       "type": "object",
       "properties":
       {
           "livestock_killed_array":{
            "title": "Livestock Killed",
            "type": "array",
            "items":
            {
                "type":"object",
                "properties":{
                    "Animal Name":{
                        "title":"Type of Livestock/ Poultry",
                        "type":"string",
                        "enum": {{enum___wildlifesightingrep_species___values}},
                        "enumNames": {{enum___wildlifesightingrep_species___names}}
                    },
                    "Number":{
                        "title":"No. of Animals",
                        "type":"number",
                        "minimum":1}
                }
            }
          },
            "wildlifesightingrep_species": {
                "type": "string",
                "title": "Species",
                "enum": {{enum___wildlifesightingrep_species___values}},
                "enumNames": {{enum___wildlifesightingrep_species___names}}
            },
           "wildlifesightingrep_numberanimals": {
                "type": "number",
                "title": "Count",
                "minimum":0
           },
           "wildlifesightingrep_collared": {
                "type": "string",
                "title": "Are Animals Collared",
                "enum": {{enum___yesno___values}},
                "enumNames": {{enum___yesno___names}}
           }

       }
   },
 "definition": [
    {
        "key":    "wildlifesightingrep_species",
        "htmlClass": "col-lg-6"
    },
    {
        "key":    "wildlifesightingrep_numberanimals",
        "htmlClass": "col-lg-6"
    },
    {
        "key":    "wildlifesightingrep_collared",
        "htmlClass": "col-lg-6"
    }
 ]
}
"""

BAD_SCHEMA = """
{
   "schema":
   {
       "$schema": "http://json-schema.org/draft-04/schema#",
       "title": "Shot Rep Report",

       "type": "object",

       "properties":
       {
            "shotrepTimeOfShot": {
                "type": "string",
                "title": "Line 1: Time when shot was heard"
            },
            "shotrepBearing": {
                "type": "number",
                "title": "Line 2: Bearing to Shot",
                "minimum": 0,
                "maximum":  360
            },
            "shotrepDistance": {
                "type": "number",
                "title": "Line 3: Distance of Shots",
                "minimum": 0
            },
            "shotrepNumberOfShots": {
                "type": "number",
                "title": "Line 4: Number of Shots",
                "minimum": 0
            },
            "shotrepTypeOfShots": {
                "type": "string",
                "title": "Line 5. Type of Shots",
                "enum": {{table__TypeOfShots__values}},
                "enumNames": {{table___TypeOfShots___names}}
            },
            "shotrepEstimatedCaliber": {
                "type": "string",
                "title": "Line 6: Estimated Caliber"
            },
            "shotrepEstimatedTarget": {
                "type": "string",
                "title": "Line 7: Estimated Target"
            }
       }
   },
 "definition": [
   {
   "key": "shotrepTimeOfShot",
   "fieldHtmlClass": "date-time-picker json-schema",
   "readonly": false
   },
   "shotrepBearing",
   "shotrepDistance",
   "shotrepNumberOfShots",
   "shotrepTypeOfShots",
   "shotrepEstimatedCaliber",
   "shotrepEstimatedTarget"
 ]
}
"""

WILDLIFE_SCHEMA_CHECKBOX = """
{
   "schema":
   {
       "$schema": "http://json-schema.org/draft-04/schema#",
       "title": "Other Wildlife Sighting Report (wildlife_sighting_rep)",

       "type": "object",
       "properties":
       {
            "wildlifesightingrep_species": {
                "type": "string",
                "title": "Species",
                "enum": {{enum___wildlifesightingrep_species___values}},
                "enumNames": {{enum___wildlifesightingrep_species___names}}
            },
           "wildlifesightingrep_numberanimals": {
                "type": "number",
                "title": "Count",
                "minimum":0
           },
           "wildlifesightingrep_collared": {
                "type": "string",
                "title": "Are Animals Collared",
                "enum": {{enum___yesno___values}},
                "enumNames": {{enum___yesno___names}}
           }

       }
   },
 "definition": [
    {
        "key":    "wildlifesightingrep_species",
        "htmlClass": "col-lg-6"
    },
    {
        "key":    "wildlifesightingrep_numberanimals",
        "htmlClass": "col-lg-6"
    },
    {
        "key":    "wildlifesightingrep_collared",
        "htmlClass": "col-lg-6"
    }
 ]
}
"""

CONFISCATION_SCHEMA = """
{
   "schema":
   {
       "$schema": "http://json-schema.org/draft-04/schema#",
       "title": "Confiscation Report (confiscation_rep)",

       "type": "object",

       "properties":
       {
            "confiscationrep_itemsconfiscated": {
                "type": "array",
                "title": "Items Confiscated",
                "items": {
					"type": "object",
					"title":"Item Details",
					"properties" : {
						"ItemConfiscated": {
						    "type": "string",
						    "title": "Item Type",
			                "enum": {{enum___confiscationrep_itemsconfiscated___values}},
			                "enumNames": {{enum___confiscationrep_itemsconfiscated___names}}
			            },
			            "ItemNumber": {
			                "type": "number",
			                "title": "Number of Items",
			                "minimum": 0
			            }
		            }
	            }
            },
            "confiscationrep_details": {
                "type": "string",
                "title": "Report Details"
            }
       }
   },
 "definition": [
    {
        "key":    "confiscationrep_itemsconfiscated",
        "add": "New",
		"style": {
		  "add": "btn-success"
		}

    },
    {
        "key":    "confiscationrep_details",
        "type":   "textarea",
        "htmlClass": "col-lg-12"
    }
 ]
}
"""

POACHERS_SCHEMA = """
{
    "schema":
    {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "EventType Test Data",

        "type": "object",

		 "properties":
         {

            "reportreportername": {
                "type": "string",
                "title": "Reporter's Name"
            },
			"reportphonenumber": {
                "type": "number",
                "title": "Telephone Number"
            },
            "event_time": {
                "title": "Event Time",
                "key": "Event Time"
            },
			 "camp_size": {
                "type": "string",
                "title": "Size of Camp",
                "enum": {{enum___camp_size___values}},
                "enumNames": {{enum___camp_size___names}}
            },
			"estimated_no_of_people": {
                "type": "number",
                "title": "Estimated Number of People"
            },
			"camp_age": {
                "type": "string",
                "title": "Age of camp",
				"enum": {{enum___camp_age___values}},
                "enumNames": {{enum___camp_age___names}}
            },
			"details_dt":{
                "title": "Details",
                "type": "array",
                "items":
                    {
                        "type":"object",
                        "properties":{

                            "infrustructure":{
                                "title": "Infrastructure",
                                "type":"string",
                                "enum": {{enum___infrustructure___values}},
                                "enumNames": {{enum___infrustructure___names}}
                                },
                                "number":{
                                "title": "Number",
                                "type":"number"
                                }
                        }
                    }
                },
            "poacherscamp_sighting_action": {
                 "key": "illegal_activities_deployed_assets"
            },
            "poachers_camp_action": {
                "key": "poacherscamp_sighting_action"
            }
		 }
	},
		 "definition": [

            {
                "type": "fieldset",
                "htmlClass": "col-lg-12",
                "items": [
                    {"key": "event_time", "fieldHtmlClass": "date-time-picker json-schema"}
                    ]
                },
                {
                "type": "fieldset",
                "title": "Reporter's Details",
                "htmlClass": "col-lg-12",
                "items": []
                },
                {
                "type": "fieldset",
                "htmlClass": "col-lg-6",
                "items": [
                "reportreportername"
                ]
                },
                {
                "type": "fieldset",
                "htmlClass": "col-lg-6",
                "items": [
                "reportphonenumber"
                ]
                },
                {
                "type": "fieldset",
                "title": "Poacher Camp Details",
                "htmlClass": "col-lg-12",
                "items": []
                },
                {
                "type": "fieldset",
                "htmlClass": "col-lg-12",
                "items": [
                "camp_size"
                ]
                },
                {
                "type": "fieldset",
                "htmlClass": "col-lg-6",
                "items": [
                "estimated_no_of_people"
                ]
                },
                {
                "type": "fieldset",
                "htmlClass": "col-lg-6",
                "items": [
                "camp_age"
                ]
                },
                {
                "type":"fieldset",
                "htmlClass":"col-lg-12",
                "items":[
                    "details_dt"
                ]
                },
                {
                "type": "fieldset",
                "title": "Action",
                "htmlClass": "col-lg-12",
                "items": []
            },
            {
                "type": "fieldset",
                "htmlClass": "col-lg-12",
                "items": [
                    {"key": "poacherscamp_sighting_action", "type": "checkboxes", "title": "Deployed Assets", "titleMap": {{enum___illegal_activities_deployed_assets___map}}}
                ]
            },
            {
                "type": "fieldset",
                "htmlClass": "col-lg-12",
                "items": [
                    {"key": "poachers_camp_action", "type": "checkboxes", "title": "Outcome", "titleMap": {{enum___poacherscamp_sighting_action___map}}}
                ]
                }

		 ]
}
"""
