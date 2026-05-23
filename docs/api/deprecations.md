# API Deprecations

This page describes how EarthRanger marks API endpoints as deprecated, the HTTP
headers we emit to advertise that status, and how clients should react. It is
the source of truth for the deprecation policy across `/api/v1.0/`.

## How to detect a deprecated endpoint

A deprecated endpoint behaves exactly like its non-deprecated form, but every
response carries three additional headers. Clients integrating with EarthRanger
should inspect these headers and react accordingly.

| Header        | RFC      | Meaning                                                                 | Example value                          |
|---------------|----------|-------------------------------------------------------------------------|----------------------------------------|
| `Deprecation` | RFC 9745 | Structured-field Date item (`@` + Unix seconds) when the endpoint was deprecated. Presence of the header is the canonical signal that the endpoint is deprecated. | `@1779494400` (2026-05-23T00:00:00Z)   |
| `Sunset`      | RFC 8594 | HTTP-date (IMF-fixdate, RFC 7231 §7.1.1.1) for when the endpoint will be removed. Treat this as the drop-dead date. | `Sun, 23 May 2027 00:00:00 GMT`        |
| `Link`        | RFC 8288 | One header carrying two comma-separated link values: `rel="successor-version"` (the canonical successor endpoint, when a 1-for-1 replacement is known) and `rel="deprecation"` (this policy doc, always present per RFC 9745 §3). | `</api/v2.0/features/>; rel="successor-version", </api/v1.0/docs/api/deprecations.html>; rel="deprecation"; type="text/html"` |

The `Deprecation` value is always less than or equal to `Sunset`. Clients that
only check one header should check `Deprecation` for "is this deprecated?" and
`Sunset` for "when must I be off this?".

## Lifecycle

EarthRanger API endpoints move through three phases:

* **Active.** No deprecation headers are emitted. The endpoint is supported and
  may evolve in backwards-compatible ways.
* **Deprecated.** The endpoint still works exactly as before. The three headers
  above are attached to every response. `Sunset` is set at least six months in
  the future, giving integrators time to migrate. The `Link` header (when
  present) names the successor endpoint.
* **Removed.** After the `Sunset` date the endpoint may be removed from the
  URL configuration. A request to a removed endpoint typically returns
  `404 Not Found`; in some cases the route may be retained briefly and return
  `410 Gone`. EarthRanger does not automatically convert a deprecated endpoint
  into a 410 at the sunset boundary — removal happens in a subsequent release.

## How to migrate

1. Read the `Link` header to find the canonical successor path. This is the
   replacement we recommend.
2. Consult the per-endpoint API reference for any payload or semantic
   differences. Successor endpoints are not guaranteed to be drop-in
   replacements — schemas, query parameters, and pagination behaviour may have
   changed.
3. If you operate a long-running client (mobile app, integration service,
   research notebook scheduled to run for months), parse the `Sunset` header at
   deploy time and surface an alert when it falls inside your maintenance
   horizon.
4. Once you have switched all callers to the successor, you can stop monitoring
   the deprecated endpoint.

A minimal client-side check looks like this:

```text
response = http.get("/api/v1.0/features/")
if response.headers.get("Deprecation"):
    successor = parse_link_header(response.headers.get("Link"))
    sunset    = parse_http_date(response.headers["Sunset"])
    log.warn("endpoint is deprecated; sunset=%s; use %s", sunset, successor)
```

## Current deprecations

The endpoints below are deprecated as of 2026-05-23 and scheduled for sunset on
2027-05-23. All paths are rooted at `/api/v1.0/` unless otherwise noted.

| Deprecated path                                       | Successor path                                  | Deprecated on | Sunset      |
|-------------------------------------------------------|-------------------------------------------------|---------------|-------------|
| `/api/v1.0/features/`                                 | `/api/v2.0/features/`                           | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/feature/<id>/`                             | `/api/v2.0/feature/<id>/`                       | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/featureset/`                               | `/api/v1.0/displaycategories/`                  | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/featureset/<id>/`                          | `/api/v1.0/displaycategory/<id>/`               | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/featureclass/`                             | `/api/v1.0/featuretypes/`                       | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/featureclass/<id>/`                        | `/api/v1.0/featuretype/<id>/`                   | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/spatialfeaturegroup/`                      | `/api/v1.0/featuregroups/`                      | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/spatialfeaturegroup/<id>/`                 | `/api/v1.0/featuregroup/<id>/`                  | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/spatialfeature/`                           | `/api/v2.0/features/`                           | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/spatialfeature/<id>/`                      | `/api/v2.0/feature/<id>/`                       | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/spatialfeatures/tiles/<z>/<x>/<y>.pbf`     | `/api/v2.0/features/tiles/<z>/<x>/<y>.pbf`      | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/maps/`                                     | `/api/v1.0/quicklinks/`                         | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/layers/`                                   | `/api/v1.0/basemaps/`                           | 2026-05-23    | 2027-05-23  |
| `/api/v1.0/layer/<id>/`                               | `/api/v1.0/basemap/<id>/`                       | 2026-05-23    | 2027-05-23  |

The successor `Link` header emitted by each endpoint uses the exact target path
listed above (with `<id>` left as a placeholder).

## References

* [RFC 9745 — The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745)
* [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594)
* [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
* [RFC 7231 §7.1.1.1 — HTTP-date](https://www.rfc-editor.org/rfc/rfc7231#section-7.1.1.1)
