## What
A single place to get the [Vault CLI](https://www.vaultproject.io/docs/commands/index.html)--zipped--for Darwin and Linux. More importantly, a `GNUmakefile` which helps you get a Vault token for use elsewhere. It even has some magic to remove soon-to-expire tokens and prompt for a fresh login... as rarely as possible!

## How
You can incorporate this into other repos by the magic of [Git Subtree](https://git-scm.com/book/en/v1/Git-Tools-Subtree-Merging)!

```sh
$ pwd
/home/you/src/some-other-git-repo-that-isn't-this-one

$ git subtree add --prefix <the-path-where-you-want-these-hooks-to-land> git@github.com:padas/vault.git master --squash
```

Need to **update** this in some other repo?

```sh
$ pwd
/home/you/src/some-other-git-repo-that-isn't-this-one

$ git subtree pull --prefix <the-path-where-you-want-this-to-land> git@github.com:padas/vault.git master --squash
```

Having done this, the **other project's** `GNUmakefile` can invoke this one. Observe:

```make
vault_makefile := <the-path-where-you-put-this>/GNUmakefile

.PHONY: foo
foo: ## some make target that needs a vault token
	@ $(MAKE) --no-print-directory --file $(vault_makefile) vault_login
  @ printf "bar\n"
```

## Wha Happen?
This repo's `vault_login` make target is there to help you log in **to Vulcan's Okta instance**. It will prompt you for your Okta credentials. Behind the scenes, this make target switches on whether or not it's running in CI. If so, does nothing (yet).

## Why (subtree this into other repos)
- the "just `git clone` and go!" experience for developer workstations... no need to install `vault`
- WYSIWYG traversing of a repo's file structure... no indirection to far-off places
- the update-all-the-things ability of a published package... but with `git`

<!-- The two trailing spaces are there to make formatting prettier -->
## What Else
- Can I use this in automation?  
**Sort of!** Why? In automation, this does nothing (yet)... but it won't break anything. So something else must be providing the caller with a Vault token.
