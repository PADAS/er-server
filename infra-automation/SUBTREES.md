<!-- The two trailing spaces are there to make formatting prettier -->
## Subtrees
They have been added via:
- infra-automation/.vulcan/terraform-subtree:  
`git subtree add --prefix infra-automation/.vulcan/terraform-subtree git@github.com:PADAS/terraform.git master --squash`
- infra-automation/.vulcan/git-hooks-subtree:  
`git subtree add --prefix infra-automation/.vulcan/git-hooks-subtree git@github.com:PADAS/git-hooks.git master --squash`
- infra-automation/.vulcan/vault-subtree:  
`git subtree add --prefix infra-automation/.vulcan/vault-subtree git@github.com:PADAS/vault.git master --squash`

In order to **update** them:
- infra-automation/.vulcan/terraform-subtree:  
`git subtree pull --prefix infra-automation/.vulcan/terraform-subtree git@github.com:PADAS/terraform.git master --squash`
- infra-automation/.vulcan/git-hooks-subtree:  
`git subtree pull --prefix infra-automation/.vulcan/git-hooks-subtree git@github.com:PADAS/git-hooks.git master --squash`
- infra-automation/.vulcan/vault-subtree:  
`git subtree pull --prefix infra-automation/.vulcan/vault-subtree git@github.com:PADAS/vault.git master --squash`
