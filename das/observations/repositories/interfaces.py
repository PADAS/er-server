from abc import ABC, abstractmethod


class ReadObservationRepositoryInterface(ABC):

    @abstractmethod
    def get_by_id(self):
        raise NotImplementedError

    @abstractmethod
    def get_observations_by_subject_id_and_source_id(self):
        raise NotImplementedError

    @abstractmethod
    def build_dataclass(self):
        raise NotImplementedError
