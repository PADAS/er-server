'''
Base objects for Analyzer code.
'''
class SubjectAnalyzer:

    def analyze(self, subject, last_result=None):
        raise NotImplementedError()