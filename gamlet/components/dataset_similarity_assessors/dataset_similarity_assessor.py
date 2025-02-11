from abc import ABC, abstractmethod
from typing import List


class DatasetSimilarityAssessor(ABC):
    """The Datasets similarity assessor is designed to assess the similarity of datasets by meta-features.

    At the knowledge acquisition stage, a table of meta-features of datasets is input.
    At the knowledge application stage, the component accepts meta-features of new datasets and
    discovers similar datasets from the previously "memorized" ones.

    Optionally, it can also return a measure of similarity (or distance) between
    the new datasets and the "memorized" ones.
    """

    @abstractmethod
    def fit(self, *args, **kwargs):
        raise NotImplementedError()

    @abstractmethod
    def predict(self, *args, **kwargs):
        raise NotImplementedError()

    @property
    @abstractmethod
    def datasets(self) -> List[str]:
        raise NotImplementedError()
