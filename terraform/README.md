# Infrastructure Migration

Meeting agenda 10/2/2019

## Completed work:
### DAS application

See all merged and closed PRs [here](https://github.com/PADAS/das/pulls?q=label%3Ainfrastructure-migration+is%3Aclosed)

- Version-locked terraform executable and Makefile conventions 
- [CircleCI build integration](https://circleci.com/gh/PADAS/das)
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
Github Repo: [terraform-gcp](https://github.com/PADAS/terraform-gcp)  
Landing spot and initial provisioning of networking infrastructure 

### Earthranger App Infra
Github Repo: [earthranger-app-infra](https://github.com/PADAS/earthranger-app-infra)  
Landing spot and initial provisioning of managed postgres and Kubernetes clusters

## Works in Progress
### DAS application
[PR out](https://github.com/PADAS/das/pull/845). 
Establish pattern for migrating templates to terraform from vcloud (awaiting approval / merge from Earthranger)


## Future Work

### TRELLO Tickets
- [TRELLO board](https://trello.com/c/ifTl6AbF/2874-modernize-existing-das-repository)

- Big picture architecture drawings
  - Graphviz repo: [das-sketch](https://github.com/PADAS/das-sketch)
	
Examples of generated artifacts (these are apt to change - please watch the repo for updates!)
### Big picture of the repos
[big picture gif](https://trello.com/c/ifTl6AbF/2874-modernize-existing-das-repository)

### Future infrastructure
[future infrastructure](https://trello.com/c/ifTl6AbF/2874-modernize-existing-das-repository)

### Directionality of the config
[config flow](https://trello.com/c/EoiR2O3Z/2875-das-repo-create-terraform-configurations)


Outstanding questions?

