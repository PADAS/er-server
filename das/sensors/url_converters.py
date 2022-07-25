class SensorKeyConverter:
    regex = r'[\w-]{3,100}'

    def to_python(self, value):
        return str(value)

    def to_url(self, value):
        return '%s' % value
