data "terraform_remote_state" "earthranger_app_infra" {
  backend   = "gcs"
  workspace = lookup(local.this_workspaces_to_infra_workspaces, terraform.workspace, local.default_infra_workspace_when_not_mapped_here)
  config = {
    bucket = "earthranger-app-infra-terraform-state-540d878e"
  }
}

