from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from ..models import AnnotationPayload, FetchedItem, PushResult


class PullConnector(ABC):
    """
    Abstract base for pulling image items from a data source.

    Implementations: LocalFileConnector, SqlConnector, RestConnector.
    """

    @abstractmethod
    def fetch_page(self, offset: int, limit: int) -> list[FetchedItem]:
        """
        Return one page of items from the data source.
        Returns an empty list when the end of the dataset is reached.
        """

    @abstractmethod
    def resolve_image(self, item: FetchedItem, local_dir: Path) -> Path:
        """
        Ensure the image is available locally and return its local path.

        - Shared-mount connector: stat() + symlink, zero copy.
        - REST connector: streaming download, skip if hash matches cached file.
        - LocalFileConnector: returns existing file path as-is.
        """

    def fetch_all(self, local_dir: Path, page_size: int = 200) -> Iterator[FetchedItem]:
        """Convenience generator that pages through the entire dataset."""
        offset = 0
        while True:
            page = self.fetch_page(offset, page_size)
            if not page:
                break
            for item in page:
                item.file_path = str(self.resolve_image(item, local_dir))
                yield item
            offset += len(page)


class PushConnector(ABC):
    """
    Abstract base for pushing annotation results back to a data source.

    Implementations: LocalFileConnector, SqlConnector, RestConnector.
    """

    @abstractmethod
    def push_batch(self, payloads: list[AnnotationPayload]) -> list[PushResult]:
        """
        Push N annotations to the data source.

        Returns a PushResult per payload. Partial failure is allowed —
        failed items should be retried via the sync queue.
        Never raises on individual item failure; only raises on fatal
        configuration errors.
        """

    @abstractmethod
    def check_remote_version(self, item_ids: list[str]) -> dict[str, str]:
        """
        Return {item_id: remote_updated_at} for conflict detection.

        Used by SyncEngine before pushing to detect whether the remote
        was modified after the local annotation session started.
        """
