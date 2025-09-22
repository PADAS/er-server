from datadog import statsd

# stackdriver tag length limit
MAX_TAG_LENGTH = 1000


def fixup_tags(tags):
    if tags is None:
        return None
    return [tag[:MAX_TAG_LENGTH] for tag in tags if tag]


def increment(metric, value=1, tags=None, sample_rate=1):
    statsd.increment(metric.lower(), value=value, tags=fixup_tags(tags), sample_rate=sample_rate)


def increment_for_view(view_name):
    statsd.increment(metric=view_name.lower())


def update_gauge(metric, value, tags=None, sample_rate=1):
    statsd.gauge(metric.lower(), value=value, tags=fixup_tags(tags), sample_rate=sample_rate)


def histogram(metric, value, tags=None, sample_rate=None):
    statsd.histogram(metric.lower(), value=value, tags=fixup_tags(tags), sample_rate=sample_rate)
