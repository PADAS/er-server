#Infrastructure Migration

## Completed work:
### DAS application
- Version-locked terraform executable and Makefile conventions 
- CircleCI build integration
- Builds on every commit
- Pushes branch-tagged images to GCR
- Consolidated the following docker builds into a single image, run with a dynamic start script:
  - API
  - MQL
  - Unittest
  - Beat 
  - Default Worker
  - Analyzer Worker
  - Notebook server
  - Realtime server
  - Realtime worker

### Terraform State Storage tooling

Provisions state storage for various terraform projects

### IAM for Build Agents

Provision Google service accounts and roles for Circle CI build agents, pushes credentials up to circle CI

### DAS application

## WIP
### DAS application
[PR out](https://github.com/PADAS/das/pull/845). 
Establish pattern for migrating templates to terraform from vcloud (awaiting approval / merge from Earthranger)


## Future Work

- Big picture architecture
  - Graphviz repo

- TRELLO board
  - Semver handling by Circle CI 
  - Provisioning namespace


Outstanding questions?

