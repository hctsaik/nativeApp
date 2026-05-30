from __future__ import annotations

from plugins.labeling.domain.core.models import AnnotationSet, ReviewDecision, utc_now_iso


VALID_ANNOTATION_SET_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"approved", "changes_requested", "rejected"},
    "changes_requested": {"draft"},
    "approved": {"deprecated"},
    "rejected": set(),
    "deprecated": set(),
}


class InvalidStateTransition(ValueError):
    pass


def transition_annotation_set(annotation_set: AnnotationSet, target_state: str) -> AnnotationSet:
    allowed = VALID_ANNOTATION_SET_TRANSITIONS.get(annotation_set.state, set())
    if target_state not in allowed:
        raise InvalidStateTransition(
            f"Cannot transition annotation set {annotation_set.id} "
            f"from {annotation_set.state} to {target_state}."
        )
    annotation_set.state = target_state  # type: ignore[assignment]
    annotation_set.version += 1
    annotation_set.updated_at = utc_now_iso()
    return annotation_set


def apply_review_decision(
    annotation_set: AnnotationSet,
    decision: str,
    actor_id: str,
    comment: str = "",
) -> ReviewDecision:
    target_state = {
        "approved": "approved",
        "rejected": "rejected",
        "changes_requested": "changes_requested",
    }.get(decision)
    if target_state is None:
        raise ValueError(f"Unsupported review decision: {decision}")
    transition_annotation_set(annotation_set, target_state)
    return ReviewDecision(
        target_type="annotation_set",
        target_id=annotation_set.id,
        target_version=annotation_set.version,
        decision=decision,  # type: ignore[arg-type]
        actor_id=actor_id,
        comment=comment,
    )
