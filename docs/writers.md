# Writing documentation for EarthRanger

## Markdown

Markdown is John Gruber's invention: a syntax to format text that is readable in its raw form and renders well to HTML. See the original [spec](https://daringfireball.net/projects/markdown/syntax).

We use CommonMark for consistent parsing. See the [CommonMark Spec (0.28)](http://spec.commonmark.org/0.28/).

Most topic and guide docs are written in Markdown (`.md`). Sphinx builds them via the MyST parser.

## reStructuredText (reST)

Some docs are in reStructuredText (`.rst`), including the main index (`index.rst`) and the API reference under `api/`. Use reST when you need Sphinx-specific features (toctrees, refs, custom roles). The [reST primer](https://www.sphinx-doc.org/en/stable/rest.html) and [quick reference](https://docutils.sourceforge.io/docs/user/rst/quickref.html) are useful.

## Setup

From the repo root:

```bash
cd docs
uv venv --python=python3.12
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
uv pip install -r requirements-docs.txt
```

Build the HTML docs:

```bash
make html
```

Output is in `docs/_build/html/`.

### Generating OpenAPI schema

From the `das/` directory (where `manage.py` lives):

```bash
python manage.py spectacular --file ../docs/_static/openapi/schema.yaml --validate --fail-on-warn
```
