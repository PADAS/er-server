

target_subject = 'DAS Green Alert: {serial} {title}'
target_from_address = 'notifications@pamdas.org'

sms_message = 'DAS Green Alert: {serial} {title}'

standalone_event_update = '''DAS {serial}: {title}
Priority: Green

  * Conservancy: Sera
  * Details: some details about the event
  * Name Of Ranger: John IsA Ranger
  * Section/Area: Corner Safi
  - Created On: {time}
  - Report Type: Other
  - Title: {title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {icon_id}'''

standalone_event_create = '''DAS {serial}: {title}
Priority: Green

  - Created On: {time}
  * Report Type: Other
  * Title: {title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {icon_id}'''

multi_update_event = '''DAS {serial}: {title}
Priority: Green

  - Created On: {time}
  - Report Type: Other
  * Title: {title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {icon_id}'''

separate_update_event_one = '''DAS {serial}: {title}
Priority: Green

  * Conservancy: Sera
  * Details: some details about the event
  * Name Of Ranger: John IsA Ranger
  * Section/Area: Corner Safi
  - Created On: {time}
  - Report Type: Other
  * Title: {title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {icon_id}'''

separate_update_event_two = '''DAS {serial}: {title}
Priority: Green

  - Conservancy: Sera
  * Details: These details have been updated
  - Name Of Ranger: John IsA Ranger
  - Section/Area: Corner Safi
  - Created On: {time}
  - Report Type: Other
  * Title: {title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {icon_id}'''

new_parent_new_child = '''DAS {parent_serial}: {parent_title}
Priority: Green

  - Created On: {parent_time}
  * Report Type: Incident Collection
  * Title: {parent_title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {parent_icon_id}



 - Contained Reports:

    - DAS {child_serial}: {child_title}
    - Priority: Green
       - Created On: {child_time}
       - Report Type: Other
       - Title: {child_title}
       - Notes: 
       - Reported By: mr_das
       - Icon Id: {child_icon_id}'''

updated_parent_unchanged_child = '''DAS {parent_serial}: {parent_title}
Priority: Green

  - Created On: {parent_time}
  - Report Type: Incident Collection
  * Title: {parent_title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {parent_icon_id}



 - Contained Reports:

    - DAS {child_serial}: {child_title}
    - Priority: Green
       - Created On: {child_time}
       - Report Type: Other
       - Title: {child_title}
       - Notes: 
       - Reported By: mr_das
       - Icon Id: {child_icon_id}'''

unchanged_parent_updated_child = '''DAS {parent_serial}: {parent_title}
Priority: Green

  - Created On: {parent_time}
  - Report Type: Incident Collection
  - Title: {parent_title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {parent_icon_id}



 - Contained Reports:

    - DAS {child_serial}: {child_title}
    - Priority: Green
       - Created On: {child_time}
       - Report Type: Other
       * Title: {child_title}
       - Notes: 
       - Reported By: mr_das
       - Icon Id: {child_icon_id}'''

standalone_deep_link = '''DAS {serial}: {title}
Priority: Green

  - Created On: {time}
  - Report Type: Other
  - Title: {title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {icon_id}
  - Subject Link: steta%3A//%3Fevent%3DOther%26name%3DRanger%20One%26sys%3Ddas%26t%3D2017-59-05T21%3A59%3A35%26lat%3D40.1353%26lon%3D-1.891517'''

nested_deep_link = '''DAS {parent_serial}: {parent_title}
Priority: Green

  - Created On: {parent_time}
  * Report Type: Incident Collection
  * Title: {parent_title}
  - Notes: 
  - Reported By: mr_das
  - Icon Id: {parent_icon_id}



 - Contained Reports:

    - DAS {child_serial}: {child_title}
    - Priority: Green
       - Created On: {child_time}
       - Report Type: Other
       - Title: {child_title}
       - Notes: 
       - Reported By: mr_das
       - Icon Id: {child_icon_id}
       - Subject Link: steta%3A//%3Fevent%3DOther%26name%3DRanger%20One%26sys%3Ddas%26t%3D2017-59-05T21%3A59%3A45%26lat%3D40.1353%26lon%3D-1.891517'''