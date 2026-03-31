# Rewrite ER authorization system
## background
Review [ER Architecture Doc](../../architecture-overview.md)
ER Server [codebase](../../..)
[Hierarchical Permissions](./hierarchical-permisions.md)

[ER Permission Types v2.0](./ER-Permission-Types-v2.0.csv)
## Existing Django permissions
Model-level CRUD permissions
we assign permissions using to a user through a PermissionSet. Each PermissionSet contains users and these CRUD permissions.
There are specialized permissions to control how a user can see subjects.
### Source Permissions
A Source is the device attached to a subject.

### Subject Permissions
Recall that a Subject is a person or animal that is carrying one or more sensors. Typically, this means there is a GPS track associated with the Subject. The following are permissions for accessing a Subject.
To see a subject, user must have permission:
* view_subject – view all description of a Subject, if this was an informant, can see name, etc.

#### Subject Group Permissions
Permissions controlling admin access to add/remove subjects from a subject group.
* delete – remove a subject from a group
* change – change permissions sets associated with a subject group
* add – add an existing Subject to this group. User must already have subject.change_view on the specific subject.
Permission to view a SubjectGroup, user permission
* view_subjectgroup - view subject group in the UI

Subjects are put in a SubjectGroup. A SubjectGroup is hierarchical, so they can include other SubjectGroups.
One or more PermissionSets are assigned to a SubjectGroup

#### Subject Track
Permissions for Track Access (array of observations for a subject)
Defines who can view a subject’s track.
Specifies any delay before the track becomes visible.
Sets limits on how far back in time the track history can be viewed.
To see tracks one delay day and one limit day permissions needs to be added to a permission set of the user. The least restrictive settings are used for all subjects the user is given permission to see.
Delay days is one of these permissions:
* observations.access_ends_0  (realtime)
* observations.access_ends_1
* observations.access_ends_3
* observations.access_ends_7*
Limit days is one of these permissions:
* observations.access_begins_7
* observations.access_begins_16
* observations.access_begins_30
* observations.access_begins_60
* observations.access_begins_all

### Event Category Permissions
Event Types are grouped in Event Categories. The following permissions are then set on the Event Category, and operate on the Event Types included in the category.
* add – add new Event
* change – change any event, add notes
* view – view events
* delete – remove an event
* admin_event – admin permission to control which users can add/change/view/delete events
*
If the site only wanted to allow a user to add and event, but not view, they would give the user “add” permission only.

## Requirements
* We want to use a rules based system, and not this hard coded model based system. Something we can create new rules without writing custom code in er server.
* This system needs to work across tenants
* **Authentication Migration**: We are migrating all of our users to authenticate through Auth0, moving away from Django's built-in authentication.
* We want a purpose built UI
* Fluent with [Hierarchical Permissions](hierarchical-permissions.md)
* We have other applications not written with Django that we want to extend our permission system to support. Being able to allow the administrator to change permissions for ER server, EcoScope and Gundi. All three apps written by our teams.
* Data warehouse support. Once we have these custom permissions on viewing subjects, need to be able to apply them to data in a data warehouse.

### Future
Things we want to solve, and not forget about when working on phase 1
* A single Serca Identity user given access to subjects in multiple sites, can see all of their subjects in ER Web

### Phase 2
The following to consider, but could be in phase 2
* Allow an organization with multiple sites to manage all of their sites
*

### UI Examples
* [Editing a subject view Permission](./images/ui_edit_subject_permission_V2.png)
* [Editing the admin permissions for a user](./images/ui_edit_admin_permission_v2.png)
* [Editing event view/edit/add permissions for user](./images/ui_edit_event_permission_v2.png)
* [Editing a role](./images/ui_edit_role_V2.png)

### Subject Permissions
For the following actions:
* Administer
* Create
* View
* Export
* Upload GPX
* Edit
* Delete
The possible conditions to test are and can be combined:
* Subject group - action on subjects in this group
* Location - action on subjects near this location
* Age of observations < or > - can view subject observations within this time frame. Because there are a billion observations, we can't put them in FGA. Once we know a user can view a subject, we need to then get the time ranges they can view subject observations. See [Subject Track](#subject-track)
* Additional data field - specific attributes of a Source, Subject, ie: Source model name
* Active - can only see Active subjects
* Subject type
* Subject sub-type

### Event Permissions


### Feature Permissions
TBD


#### Authentication & Organization Structure
* **auth0_organization** - Auth0 Organization is a one to one mapping to a tenant in ER
* **tenant** - ER site/tenant (managed by an Auth0 Organization)
* **user** - Auth0 user (identified by Auth0 user ID, e.g., auth0|123456)
* **user_group** - Groups of users for permission management

#### Core ER Resources
* subject
* subject_group
* source
* source_group
* source_provider
* message
* event
* eventtype
* eventcategory
* patrol
* patrol_type
* alert
* choice
* feature
* feature_group
* feature_class




## Resources
### Docs
[ER Permission Types v2.0 Original](https://docs.google.com/spreadsheets/d/15j3NzohJYbrdWyLTA14O3uzGNliCGXYtGvOMXXDAkv4/edit?usp=sharing)

### Auth0 Authentication
- **Auth0 Authentication Docs**: https://auth0.com/docs/authenticate
- **Auth0 Organizations**: https://auth0.com/docs/manage-users/organizations
- **Auth0 Python SDK**: https://github.com/auth0/auth0-python
