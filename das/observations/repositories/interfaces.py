from abc import ABC, abstractmethod


class RepositoryInterface(ABC):
    @abstractmethod
    def get_all(self):
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self):
        raise NotImplementedError

    @abstractmethod
    def build_dataclass(self):
        raise NotImplementedError
