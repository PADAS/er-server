

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
  - Reported By: mr_das'''

standalone_event_create = '''DAS {serial}: {title}
Priority: Green

  - Created On: {time}
  * Report Type: Other
  * Title: {title}
  - Notes: 
  - Reported By: mr_das'''

multi_update_event = '''DAS {serial}: {title}
Priority: Green

  - Created On: {time}
  - Report Type: Other
  * Title: {title}
  - Notes: 
  - Reported By: mr_das'''

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
  - Reported By: mr_das'''

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
  - Reported By: mr_das'''

new_parent_new_child = '''DAS {parent_serial}: {parent_title}
Priority: Green

  - Created On: {parent_time}
  * Report Type: Incident Collection
  * Title: {parent_title}
  - Notes: 
  - Reported By: mr_das


 - Contained Reports:

    - DAS {child_serial}: {child_title}
    - Priority: Green
       - Created On: {child_time}
       - Report Type: Other
       - Title: {child_title}
       - Notes: 
       - Reported By: mr_das'''

updated_parent_unchanged_child = '''DAS {parent_serial}: {parent_title}
Priority: Green

  - Created On: {parent_time}
  - Report Type: Incident Collection
  * Title: {parent_title}
  - Notes: 
  - Reported By: mr_das


 - Contained Reports:

    - DAS {child_serial}: {child_title}
    - Priority: Green
       - Created On: {child_time}
       - Report Type: Other
       - Title: {child_title}
       - Notes: 
       - Reported By: mr_das'''

unchanged_parent_updated_child = '''DAS {parent_serial}: {parent_title}
Priority: Green

  - Created On: {parent_time}
  - Report Type: Incident Collection
  - Title: {parent_title}
  - Notes: 
  - Reported By: mr_das


 - Contained Reports:

    - DAS {child_serial}: {child_title}
    - Priority: Green
       - Created On: {child_time}
       - Report Type: Other
       * Title: {child_title}
       - Notes: 
       - Reported By: mr_das'''
