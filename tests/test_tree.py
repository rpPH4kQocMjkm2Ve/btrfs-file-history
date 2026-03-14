"""Tests for btrfs_file_history/tree.py — pure logic only."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from btrfs_file_history.tree import SubvolumeTree
from btrfs_file_history.btrfs import Subvolume


def _sv(subvol_id: int, path: str, uuid: str,
        parent_uuid: str = None, ogen: int = 0) -> Subvolume:
    return Subvolume(
        subvol_id=subvol_id,
        gen=ogen,
        ogen=ogen,
        top_level=5,
        path=path,
        uuid=uuid,
        parent_uuid=parent_uuid,
        received_uuid=None,
        is_snapshot=(parent_uuid is not None),
    )


class TestValidateRelative:
    def test_normal(self):
        assert SubvolumeTree._validate_relative("etc/fstab") == "etc/fstab"

    def test_leading_slash_stripped(self):
        assert SubvolumeTree._validate_relative("/etc/fstab") == "etc/fstab"

    def test_traversal_rejected(self):
        import pytest
        with pytest.raises(ValueError):
            SubvolumeTree._validate_relative("../etc/passwd")

    def test_mid_traversal_rejected(self):
        import pytest
        with pytest.raises(ValueError):
            SubvolumeTree._validate_relative("usr/../etc/passwd")

    def test_empty(self):
        assert SubvolumeTree._validate_relative("") == ""

    def test_dot(self):
        assert SubvolumeTree._validate_relative("/") == ""
