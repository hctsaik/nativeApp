from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FetchedItem:
    """An image item returned by a PullConnector."""
    item_id:   str
    file_path: str            # local abs path; empty until resolve_image() is called
    image_url: str | None     # populated by URL-based connectors; None for mount connectors
    width:     int | None
    height:    int | None
    file_hash: str | None     # remote md5 for cache validation
    metadata:  dict = field(default_factory=dict)  # arbitrary pass-through


@dataclass
class AnnotationPayload:
    """Annotation result ready to be pushed to a remote data source."""
    item_id:        str
    remote_id:      str           # original remote PK from FetchedItem.metadata["remote_id"]
    image_path:     str           # basename only
    image_width:    int
    image_height:   int
    shapes:         list[dict]    # X-AnyLabeling shape objects verbatim
    classification: str | None
    confidence:     float | None
    annotator:      str           # "manual" | "model" | "xanylabeling"
    annotated_at:   str           # ISO-8601 UTC


@dataclass
class PushResult:
    """Result of pushing one annotation payload."""
    item_id:    str
    success:    bool
    remote_ref: str | None  # server-assigned id; used as idempotency key on retry
    error:      str | None
