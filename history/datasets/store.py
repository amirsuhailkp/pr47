"""In-memory historical dataset store (Phase 3 scaffold).

A durable version (Parquet/blob storage per docs/DATA_MODEL.md §Storage) replaces the
dict backing this without changing the interface. The core rule enforced here:
no dataset is stored or retrievable without a valid DatasetManifest, and nothing is
ever silently dropped from a stored setup — reproducibility over convenience.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.history import DatasetManifest, HistoricalSetup


class DatasetNotFoundError(Exception):
    pass


@dataclass
class HistoricalDataset:
    manifest: DatasetManifest
    setups: list[HistoricalSetup] = field(default_factory=list)

    def __post_init__(self) -> None:
        mismatched = [
            s for s in self.setups if s.dataset_version != self.manifest.dataset_version
        ]
        if mismatched:
            raise ValueError(
                f"{len(mismatched)} setup(s) have a dataset_version that doesn't match "
                "this dataset's manifest — every setup must be traceable to its manifest"
            )


class DatasetStore:
    def __init__(self) -> None:
        self._datasets: dict[str, HistoricalDataset] = {}

    def save(self, dataset: HistoricalDataset) -> str:
        content_hash = dataset.manifest.content_hash()
        self._datasets[dataset.manifest.dataset_version] = dataset
        return content_hash

    def get(self, dataset_version: str) -> HistoricalDataset:
        try:
            return self._datasets[dataset_version]
        except KeyError as exc:
            raise DatasetNotFoundError(dataset_version) from exc

    def list_versions(self) -> list[str]:
        return list(self._datasets.keys())
