from datadog import statsd


def increment(metric, value=1, tags=None, sample_rate=1):
    statsd.increment(metric.lower(), value=value,
                     tags=tags, sample_rate=sample_rate)


def increment_for_view(view_name):
    statsd.increment(metric=view_name.lower())


def update_gauge(metric, value, tags=None, sample_rate=1):
    statsd.gauge(metric.lower(), value=value,
                 tags=tags, sample_rate=sample_rate)


def histogram(metric, value, tags=None, sample_rate=None):
    statsd.histogram(metric.lower(), value=value,
                     tags=tags, sample_rate=sample_rate)
