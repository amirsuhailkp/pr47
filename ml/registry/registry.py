"""In-memory model registry (Phase 5 scaffold — a durable store replaces the dict
backing this later without changing the interface).

Promotion is deliberate and logged: a model only reaches PRODUCTION via an explicit
promote() call, and only if its stored ValidationResult says it's eligible
(leakage tests passed AND it beats its baseline) — never automatically on training.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.domain.ml import ModelManifest, ModelStatus, RegistryEntry, ValidationResult


class ModelNotFoundError(Exception):
    pass


class PromotionNotEligibleError(Exception):
    pass


class ModelRegistry:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], RegistryEntry] = {}

    def register(self, manifest: ModelManifest, validation: ValidationResult | None = None) -> None:
        key = (manifest.task, manifest.model_version)
        self._entries[key] = RegistryEntry(manifest=manifest, validation=validation)

    def record_validation(self, task: str, model_version: str, validation: ValidationResult) -> None:
        entry = self._get(task, model_version)
        entry.validation = validation

    def promote(self, task: str, model_version: str, now: datetime | None = None) -> None:
        entry = self._get(task, model_version)
        if entry.validation is None or not entry.validation.eligible_for_promotion:
            raise PromotionNotEligibleError(
                f"{task}:{model_version} is not eligible for promotion "
                "(missing validation, failed leakage tests, or did not beat baseline)"
            )
        # Retire any currently-production model for this task first.
        for (t, v), e in self._entries.items():
            if t == task and e.status == ModelStatus.PRODUCTION:
                e.status = ModelStatus.RETIRED

        entry.status = ModelStatus.PRODUCTION
        entry.promoted_at = now or datetime.now(timezone.utc)

    def reject(self, task: str, model_version: str) -> None:
        entry = self._get(task, model_version)
        entry.status = ModelStatus.REJECTED

    def production_model(self, task: str) -> RegistryEntry | None:
        for (t, _), e in self._entries.items():
            if t == task and e.status == ModelStatus.PRODUCTION:
                return e
        return None

    def get(self, task: str, model_version: str) -> RegistryEntry:
        return self._get(task, model_version)

    def _get(self, task: str, model_version: str) -> RegistryEntry:
        try:
            return self._entries[(task, model_version)]
        except KeyError as exc:
            raise ModelNotFoundError(f"{task}:{model_version}") from exc
