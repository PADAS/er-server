# Infrastructure Migration

## Completed work:
### DAS application

See all merged and closed PRs here:
  - Github [infrastructure-migration](https://github.com/PADAS/das/pulls?q=label%3Ainfrastructure-migration+is%3Aclosed) label

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

Github Repo: [terraform-state-storage](https://github.com/PADAS/terraform-state-storage)
Provisions state storage for various terraform projects

### IAM for Build Agents

Github Repo: [iam-for-build-agents](https://github.com/PADAS/iam-for-build-agents)
Provision Google service accounts and roles for Circle CI build agents, pushes credentials up to circle CI

### Terraform GCP
Github Repo: [terraform-gcp] (https://github.com/PADAS/terraform-gcp)
Landing spot and initial provisioning of networking infrastructure, 

### Earthranger App Infra
Github Repo: [earthranger-app-infra](https://github.com/PADAS/earthranger-app-infra)
Landing spot and initial provisioning of managed postgres and Kubernetes clusters

### DAS application

## WIP
### DAS application
[PR out](https://github.com/PADAS/das/pull/845). 
Establish pattern for migrating templates to terraform from vcloud (awaiting approval / merge from Earthranger)


## Future Work

- Big picture architecture
  - Graphviz repo
	
Examples of generated artefacts (these are apt to change - please watch the repo for updates!



- TRELLO board
  - Semver handling by Circle CI 
  - Provisioning namespace


Outstanding questions?

