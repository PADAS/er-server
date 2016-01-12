from django.contrib.gis.db import models


class Analyzer(models.Model):
    min_time = models.TimeField(null=True)
    max_time = models.TimeField(null=True)

    class Meta:
        abstract = True

    @property
    def valid_times(self):
        return self._valid_times or (self.min_time, self.max_time)


class AnalyzerResult():
    value = 0.0
    analyzer_type = None
