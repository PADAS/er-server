import pymet
from observations.models import SubjectTrackSegmentFilter
from analyzers.models import SubjectAnalyzerResult

'''
Base objects for Analyzer code.
'''


class SubjectAnalyzer:

    def __init__(self, subject=None, config=None):
        self.config = config
        if subject.get('is_active', None):
            self.subject = subject
        else:
            raise Exception('Error while initializing analyzer due to inactive'
                            ' subject = {}'.format(subject.get('name')))

    def analyze_trajectory(self, traj=None):
        raise NotImplementedError()

    def save_analyzer_result(self, last_result=None, this_result=None):
        raise NotImplementedError()

    def create_analyzer_event(self, last_result=None, this_result=None):
        raise NotImplementedError()

    def default_observations(self):
        """
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        """
        raise NotImplementedError()

    def get_last_result(self):
        try:
            last_result = SubjectAnalyzerResult.objects.filter(subject=self.subject,
                                                               subject_analyzer_id=self.config.id). \
                latest('estimated_time')
        except SubjectAnalyzerResult.DoesNotExist:
            last_result = None

        return last_result

    def analyze(self, observations=None, trajectory_filter=None):

        # Get default observations list if one isn't provided
        observations = observations or self.default_observations()

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.subject.default_trajectory_filter()

        # Create Trajectory which is the input to the analysis.
        trajectory = self.subject.create_trajectory(obs=observations,
                                                    trajectory_filter_params=trajectory_filter)

        results = self.analyze_trajectory(trajectory)

        analyze_results = []

        for this_result in results:

            # Get the last analyzer result
            last_result = self.get_last_result()

            # Save the current result in the context of the last result saved
            self.save_analyzer_result(last_result=last_result, this_result=this_result)

            # Create an event based on the result
            this_event = self.create_analyzer_event(last_result=last_result, this_result=this_result)

            analyze_results.append((this_result, this_event))

        return analyze_results

    class Meta:
        abstract = True
        app_label = 'subject_analyzer'
