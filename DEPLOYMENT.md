# das/infra-automation
Deployment code for instantiating a DAS site.

That is, `./infra-automation` is where you'll execute most commands. `./terraform` is where you'll find resource definitions. 
And `./templated-deployment` is where you'll find resources for generation k8s yamls.

## Prerequisites
TODO: Add details for how to prepare a workstation environment for using the scripts herein.

Ensure your local `kubectl` is using the intended cluster . You can check the active configuration by using:

```bash
kubectl config current-context
```

E.g for the dev cluster you should get:

> gke_earthranger-78ca55ca_us-west1-a_das-dev

## Example: Create a new EarthRanger site

Use these steps to create a new EarthRanger site on our development infrastructure.

This will create:
* a new database within our existing development Postgresql server.
* a new kubernetes namespace on our development cluster
* other resources including a Routee53 record for the site

1. Change dir in to ./infra-automation
2. Run `make` to see descriptions of make targets
3. Run `make tf_workspace_new workspace="cheesepuff"`  **This will ultimately result in a site at https://cheesepuff.pamdas.org. You'll probably want to use a different workspace name me.**
4. Run `make tf_plan`
5. Run `make tf_apply`
   a. Note: this might required you to create a firewall hole to allow your workstation to access your new bastion server using ssh. See below for notes.
6. Run `make generate_manifest -e current_branch=1_87_1`
7. Run `make render_templates`
8. Run `make kubectl_apply`

At the end of these steps you'll have a site at https://{workspace}.pamdas.org and you can sign into it using the well-known default `admin` credentials.

### Add firewall rule for ssh access to bastion server
In order to complete the steps above from your workstation, you'll likely need to create a firewall rule allowing access to the bastion server (a VM) that gets created as part of the deployment process.

To set that...

Run:

```
gcloud compute firewall-rules create "some-uniq-name" --allow="tcp:22" \
  --description="Delete me." --direction=INGRESS --network=dev --priority=899 \
  --source-ranges="$(curl --silent ifconfig.io)/32" \
  --target-tags="psql-bastion" --project="earthranger-78ca55ca"
```

And delete the firewall rule after your deployment.

