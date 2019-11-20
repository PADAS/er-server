<!-- The two trailing spaces are there to make formatting prettier -->
## Subtrees
They have been added via:
- .vulcan/terraform-subtree:  
`git subtree add --prefix .vulcan/terraform-subtree git@github.com:CoralMapping/terraform.git master --squash`
- .vulcan/git-hooks-subtree:  
`git subtree add --prefix .vulcan/git-hooks-subtree git@github.com:CoralMapping/git-hooks.git master --squash`
- .vulcan/vault-subtree:  
`git subtree add --prefix .vulcan/vault-subtree git@github.com:CoralMapping/vault.git master --squash`

In order to **update** them:
- .vulcan/terraform-subtree:  
`git subtree pull --prefix .vulcan/terraform-subtree git@github.com:CoralMapping/terraform.git master --squash`
- .vulcan/git-hooks-subtree:  
`git subtree pull --prefix .vulcan/git-hooks-subtree git@github.com:CoralMapping/git-hooks.git master --squash`
- .vulcan/vault-subtree:  
`git subtree pull --prefix .vulcan/vault-subtree git@github.com:CoralMapping/vault.git master --squash`
