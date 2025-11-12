# Writing documentation for EarthRanger

## Markdown

Markdown is of John Gruber's invention to provide a syntax to format text
that would be understandable in it's raw syntax and better when rendered
to HTML. Here is the original [spec](https://daringfireball.net/projects/markdown/syntax).

We enforce proper Markdown syntax through CommonMark.
Here is CommonMark Spec [version 0.28](http://spec.commonmark.org/0.28/)

## RST


## Setup
cd docs  # this directory
```
uv venv --python=python3.12
uv pip install -r requirements-docs.txt
```

### generating openapi schema
```
python manage.py spectacular --file ../docs/_static/openapi/schema.yaml --validate --fail-on-warn
```
