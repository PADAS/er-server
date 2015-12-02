from abc import ABCMeta, abstractmethod


class Analyzer(metaclass=ABCMeta):

    @abstractmethod
    def analyze(*args, **kwargs): pass


class AnalyzerResult():
    value = 0.0
    analyzer_type = None
