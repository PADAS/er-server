from datadog import statsd


def increment(metric, value=1, tags=None, sample_rate=1):
    statsd.increment(metric, value=value, tags=tags, sample_rate=sample_rate)
