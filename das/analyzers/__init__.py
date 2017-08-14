import pymet.base
import pymet.cluster

'''
Base objects for Analyzer code.
'''


class SubjectAnalyzer:

    def analyze(self, subject, last_result=None):
        raise NotImplementedError()

    def _create_trajectory(self, observations, trajectory_filter_params=None):
        """
        Hydrate the trajectory
        """
        def create_fix(observation):
            gp = pymet.base.GeoPoint(
                observation.location.x, observation.location.y, 0.0)
            fix = pymet.base.Fix(gp, observation.recorded_at)
            return fix

        # Create a relocations object
        fixes = [create_fix(x) for x in observations]
        relocs = pymet.base.Relocations(fixes)

        # Filter the relocations for junk coordinates
        coord_filter = pymet.base.RelocsCoordinateFilter()
        relocs.apply_fix_filter(coord_filter)

        # Filter the relocations based on speed
        speed_threshold = float('Inf')

        if trajectory_filter_params is not None:
            speed_threshold = trajectory_filter_params.speed_KmHr
        speed_filter = pymet.base.RelocsSpeedFilter(
            max_speed_kmhr=speed_threshold)
        relocs.apply_fix_filter(speed_filter)

        # Create a trajectory from the relocations
        traj = pymet.base.Trajectory(relocs)

        return traj
