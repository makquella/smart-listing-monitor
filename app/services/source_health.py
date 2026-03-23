from statistics import median

from app.core.config import Settings
from app.services.types import HealthEvaluation


class SourceHealthService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def baseline_from_history(self, counts: list[int]) -> int | None:
        if not counts:
            return None
        return int(median(counts))

    def evaluate(
        self, *, item_count: int, warnings: list[str], recent_healthy_counts: list[int]
    ) -> HealthEvaluation:
        baseline = self.baseline_from_history(recent_healthy_counts)

        if item_count <= 0:
            return HealthEvaluation(status="failing", parse_completeness_ratio=0.0)

        if warnings:
            return HealthEvaluation(
                status="degraded",
                parse_completeness_ratio=1.0 if baseline is None else item_count / baseline,
            )

        if baseline is None or baseline == 0:
            return HealthEvaluation(status="healthy", parse_completeness_ratio=1.0)

        ratio = item_count / baseline
        if ratio < self.settings.degraded_parse_ratio_threshold:
            return HealthEvaluation(status="degraded", parse_completeness_ratio=ratio)

        return HealthEvaluation(status="healthy", parse_completeness_ratio=ratio)
