## What
A single place to get [Terraform](https://www.terraform.io/intro/index.html)--zipped--for Darwin and Linux. More importantly, a `GNUmakefile` which helps you use Terraform in other projects.

## How
You can incorporate this into other repos by the magic of [Git Subtree](https://git-scm.com/book/en/v1/Git-Tools-Subtree-Merging)!

```sh
$ pwd
/home/you/src/some-other-git-repo-that-isn't-this-one

$ git subtree add --prefix <the-path-where-you-want-these-hooks-to-land> git@github.com:das/terraform.git master --squash
```

Need to **update** this in some other repo?

```sh
$ pwd
/home/you/src/some-other-git-repo-that-isn't-this-one

$ git subtree pull --prefix <the-path-where-you-want-this-to-land> git@github.com:das/terraform.git master --squash
```

Having done this, the **other project's** `GNUmakefile` can invoke this one. Observe:

```make
terraform_makefile := <the-path-where-you-put-this>/GNUmakefile

.PHONY: foo
foo: ## invoke a make target (terraform_version in this case) in the subtree'd repo's GNUmakefile
	@ $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_version

# you can pass arguments... provided they are defined in this repo's GNUmakefile
.PHONY: bar
bar: ## invoke a make target (terraform_fmt in this case) in the subtree'd repo's GNUmakefile... with arguments
	@ $(MAKE) --no-print-directory --file $(terraform_makefile) terraform_fmt fmt_options="-recursive"
```

## Why (subtree this into other repos)
- the "just `git clone` and go!" experience for developer workstations... no need to install `terraform`
- WYSIWYG traversing of a repo's file structure... no indirection to far-off places
- the update-all-the-things ability of a published package... but with `git`
