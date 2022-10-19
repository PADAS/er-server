# Python Coding Style

## Zen of Python

Beautiful is better than ugly.
Explicit is better than implicit.
Simple is better than complex.
Complex is better than complicated.
Flat is better than nested.
Sparse is better than dense.
Readability counts.
Special cases aren't special enough to break the rules.
Although practicality beats purity.
Errors should never pass silently.
Unless explicitly silenced.
In the face of ambiguity, refuse the temptation to guess.
There should be one-- and preferably only one --obvious way to do it.
Although that way may not be obvious at first unless you're Dutch.
Now is better than never.
Although never is often better than _right_ now.
If the implementation is hard to explain, it's a bad idea.
If the implementation is easy to explain, it may be a good idea.
Namespaces are one honking great idea -- let's do more of those!

[PEP 20](https://legacy.python.org/dev/peps/pep-0020/)

## Python Coding Conventions

- PEP 8 -- Style Guide for Python Code
- Spaces not tabs, 4 space indents
- Maximum line length less than 80
- Doc strings less than 72
- Line breaks before operators
- Here is a biased view of using [PEP8](https://pep8.org/)

## Comments and Documentation

We use the Google standard for docstring generation for functions and classes. Docstrings are explored in depth here in [PEP 0257](https://www.python.org/dev/peps/pep-0257/).

VSCode has a recommended docstring generator which can be found [here](https://marketplace.visualstudio.com/items?itemName=njpwerner.autodocstring).

## Python Type Hints

As supported since Python 3.5, we can now annotate our code to express types for all function arguments, return values and more generally data structures. This is not enforced at run-time, but most modern IDEs with python extensions can warn when types are crossed.

It is recommended that new code expresses types. See [type hints](https://docs.python.org/3.7/library/typing.html).

## Managing python requirements

We use uv to manage our requirements so that project and all dependent python packages are pinned to a specific version.

The canonical list of packages required for the project are contained in `pyproject.toml`. Pinned versions are tracked in `uv.lock`.

Install requirements:
```bash
uv sync --group dev
```

## Dependabot Alerts

All python repos with requirements.txt files should be registered for [Dependabot Alerts](https://docs.github.com/en/code-security/dependabot/dependabot-security-updates/about-dependabot-security-updates) through Github. We are going to update them following our standard task and PR process. If there are several alerts, group them first by Major and Minor updates. We consider Major version changes as something requiring more review and regression testing than minor updates. Thus, let us group library updates with major changes in separate PRs than ones with minor changes. Note this major or minor effort in the Jira ticket associated so that we can communicate potential risk to the team. For Major library version changes, review the change logs and document concerning changes in the Jira ticket.
