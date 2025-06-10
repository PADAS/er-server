# EarthRanger Architecture

![Architecture Overview](../images/er_architecture_overview.jpeg)

## Observations
### SubjectStatus
The SubjectStatus record for a Subject holds the latest movement and status of the radio that subject is assigned.

#### Real-time Updates
When a new Observation is added to the database, the following process occurs:

1. Identify the Source of the new Observation
2. Find the Subject that has this Source assigned during the Observation's `recorded_at` time by checking the `SubjectSource.assigned_range`
3. Verify that the identified SubjectSource is the active record for the Subject during that time period
4. Confirm this Observation is the most recent one by:
   - Searching the Observation table for this Source within the assigned_range. We want the most recent in the assigned_range for this Source
   - If the Observation's Source is currently assigned to the subject, we can optimize this search by getting the Observation from the LatestObservationSource table.
5. Update the Subject's SubjectStatus record with the new Observation data

#### Daily Maintenance
A nightly job runs to ensure SubjectStatus records remain accurate. For each Subject:

1. Iterate through the Subject's assigned SubjectSource records, ordered by descending `assigned_range`
2. Find the most recent non-excluded Observation for each Source
3. Update the SubjectStatus record with the most recent valid Observation
   - Typically found within the current SubjectSource assigned_range
   - May require checking previous assigned_range windows if no recent Observation exists
