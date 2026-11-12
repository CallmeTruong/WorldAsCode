import shutil

import pytest

from worldascode.config import paths
from worldascode.kits.context import cards
from worldascode.kits.registry import Library, package_files


def test_builtin_cards_and_nested_release_files_are_preserved(tmp_path):
    library = Library(tmp_path / "library")
    library.initialize()
    folder, _ = library.resolve()
    assert "roofs" in cards(folder / "kit-api.md")
    assert any(path.parent.name == "api" for path in package_files(folder))
    assert (folder / "api/roofs.md").read_bytes() == (
        paths().runtime_dir / "api/roofs.md"
    ).read_bytes()


def test_modified_api_card_is_rejected(tmp_path):
    folder = tmp_path / "kit"
    shutil.copytree(paths().runtime_dir, folder)
    with (folder / "api/roofs.md").open("a", encoding="utf-8") as stream:
        stream.write("\nUnverified instructions")
    with pytest.raises(ValueError, match="KIT_DOCUMENT_HASH_MISMATCH"):
        cards(folder / "kit-api.md")
