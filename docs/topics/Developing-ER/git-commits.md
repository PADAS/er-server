# Git Commits

## Why conventional commits?

The lack of a convention to write commits and pretty messy history logs led us to write this document that will help us with the following:

- Have aesthetic and better understandable commits.
- Advantage of making cherry-picks easily.
- Readable commit messages.
- Generation of a `changelog`.
- This leads us to use an atomic commit workflow.

| **Type** | **Description** | **Use Cases** |
| --- | --- | --- |
| **feat** | Introduces a new feature to the codebase. | Introduce new code (exclude configurations and fixes) |
| **fix** | Fixes a bug in your codebase | Modify existing code (exclude configurations) |
| **chore** | Includes a technical or preventative maintenance task. | Modify or add files that enable a feature flag, upgrade of the project version, configurations formatting, architecture files, etc. |
| **test** | Adding missing tests or correcting existing tests | For those types of files that follow the next format: `test_*.py`, `tests_*.py`, `conftest.py`, `factories.py` |
| **style** | Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc) | When the change in the files is related to formatting or cleaning. |

> If any type commit includes a **Breaking Change** we need to add a bang `(!)` after the type name. Example: `feat!: my awesome feature broke something`

## Syntax or conventions

```
<type>[scope(optional)]: <description> (Max 72 chars per line)


[body(optional)]


[footer(optional)]
```

- **type**: defined previously
- **scope** (optional): provides additional contextual information, for example, the Django app name (`utils`, `rt_api`)
- **description**: contains a short description about the changes made in the commit (it should look like a title)
  - Is a **mandatory** part of the format
  - Use the imperative, present tense: "change" not "changed" nor "changes", "add", "modify", "delete", "remove"
  - Don't capitalize the first letter
  - No dot (.) at the end
- **body** (optional): should include the motivation for the change and contrast this with previous behavior.
  - Use the imperative, present tense: "change" not "changed" nor "changes"
  - This is the place to mention issue identifiers and their relations.
- **footer** (optional): should contain any information about **Breaking Changes** and is also the place to **reference Issues** that this commit refers to. Collaborators (pair programming).
  - **Optionally** reference an issue by its id.
  - **Breaking Changes** should start with the word `BREAKING CHANGES:` followed by space or two newlines. The rest of the commit message is then used for this.

## Examples

```
feat[utils]: add schema generator tool


This need to be used from now in all schemas related task


ft @juan @aza @diego @frank
```

```
fix[observations]: broken url dispatcher
```

```
chore: upgrade project version to 2.6.1
```

## References

- https://www.conventionalcommits.org/en/v1.0.0/
- https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13
- https://medium.com/neudesic-innovation/conventional-commits-a-better-way-78d6785c2e08
