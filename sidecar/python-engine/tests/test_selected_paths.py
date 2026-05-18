from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import SelectedPathStore


@pytest.fixture
def store(tmp_path: Path) -> SelectedPathStore:
    return SelectedPathStore(tmp_path / "data" / "selected_paths.json")


def test_initial_paths_empty(store: SelectedPathStore) -> None:
    assert store.get_paths() == []


def test_set_and_get_round_trips(store: SelectedPathStore) -> None:
    paths = [r"C:\data\file.csv", r"C:\data\other.csv"]
    store.set_paths(paths)
    result = store.get_paths()
    assert len(result) == len(paths)
    for original, retrieved in zip(paths, result):
        assert Path(retrieved) == Path(original)


def test_overwrite_replaces_previous(store: SelectedPathStore) -> None:
    store.set_paths([r"C:\old.csv"])
    store.set_paths([r"C:\new.csv"])
    result = store.get_paths()
    assert len(result) == 1
    assert Path(result[0]) == Path(r"C:\new.csv")


def test_set_empty_clears_paths(store: SelectedPathStore) -> None:
    store.set_paths([r"C:\file.csv"])
    store.set_paths([])
    assert store.get_paths() == []


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    store = SelectedPathStore(tmp_path / "nonexistent" / "paths.json")
    store._path.unlink(missing_ok=True)
    assert store.get_paths() == []


def test_corrupt_file_returns_empty(store: SelectedPathStore) -> None:
    store._path.write_text("not valid json", encoding="utf-8")
    assert store.get_paths() == []


def test_file_created_on_init(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "paths.json"
    SelectedPathStore(path)
    assert path.exists()
