from app.models.monitor_profile import MonitorProfile
from app.models.run import MonitoringRun
from app.models.source import Source
from app.services.monitor_evaluator import EvaluatedMonitorMatch


class DigestBuilder:
    def build_run_digest(
        self,
        *,
        profile: MonitorProfile,
        source: Source,
        run: MonitoringRun,
        matches: list[EvaluatedMonitorMatch],
        summary_text: str,
    ) -> str:
        top_matches = matches[:3]
        lines = [
            f"Monitoring Digest: {profile.name}",
            f"Source: {source.name}",
            f"Run: #{run.id} ({run.status}) in {round((run.duration_ms or 0) / 1000, 1)}s",
            (
                f"Scanned: {run.items_parsed} | New: {run.new_items_count} | "
                f"Changed: {run.changed_items_count} | Removed: {run.removed_items_count}"
            ),
            "Top matches:",
        ]
        for index, match in enumerate(top_matches, start=1):
            lines.append(f"{index}. [{match.draft.priority.upper()}] {match.event.summary_text}")
        lines.extend(
            [
                "Gemini summary:",
                summary_text,
            ]
        )
        return "\n".join(lines)
