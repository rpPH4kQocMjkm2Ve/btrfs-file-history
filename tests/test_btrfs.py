"""Tests for btrfs_file_history/btrfs.py — pure parsing functions."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from btrfs_file_history.btrfs import (
    _parse_subvol_line,
    _uuid_or_none,
    ExtentInfo,
    _EXTENT_RE,
)


class TestUuidOrNone:
    def test_dash(self):
        assert _uuid_or_none("-") is None

    def test_empty(self):
        assert _uuid_or_none("") is None

    def test_whitespace(self):
        assert _uuid_or_none("   ") is None

    def test_valid(self):
        assert _uuid_or_none("abc-123") == "abc-123"

    def test_strips_whitespace(self):
        assert _uuid_or_none("  abc-123  ") == "abc-123"


class TestParseSubvolLine:
    def test_standard_line(self):
        line = (
            "ID 256 gen 100 cgen 50 top level 5 "
            "parent_uuid - received_uuid - "
            "uuid aaaa-bbbb-cccc "
            "path rootfs"
        )
        r = _parse_subvol_line(line)
        assert r is not None
        assert r["id"] == "256"
        assert r["gen"] == "100"
        assert r["ogen"] == "50"
        assert r["top_level"] == "5"
        assert r["uuid"] == "aaaa-bbbb-cccc"
        assert r["parent_uuid"] == "-"
        assert r["path"] == "rootfs"

    def test_snapshot_line(self):
        line = (
            "ID 300 gen 150 cgen 120 top level 5 "
            "parent_uuid aaaa-bbbb-cccc received_uuid - "
            "uuid dddd-eeee-ffff "
            "path snapshots/daily.1"
        )
        r = _parse_subvol_line(line)
        assert r is not None
        assert r["id"] == "300"
        assert r["parent_uuid"] == "aaaa-bbbb-cccc"
        assert r["path"] == "snapshots/daily.1"

    def test_path_with_spaces(self):
        line = (
            "ID 400 gen 200 cgen 200 top level 5 "
            "parent_uuid - received_uuid - "
            "uuid 1111-2222 "
            "path my snapshot dir/sub dir"
        )
        r = _parse_subvol_line(line)
        assert r is not None
        assert r["path"] == "my snapshot dir/sub dir"

    def test_fs_tree_prefix(self):
        """Path starting with <FS_TREE>/ is handled by caller, parser keeps it."""
        line = (
            "ID 256 gen 100 cgen 50 top level 5 "
            "parent_uuid - received_uuid - "
            "uuid aaa-bbb "
            "path <FS_TREE>/rootfs"
        )
        r = _parse_subvol_line(line)
        assert r is not None
        assert r["path"] == "<FS_TREE>/rootfs"

    def test_too_short(self):
        assert _parse_subvol_line("ID 256") is None

    def test_empty(self):
        assert _parse_subvol_line("") is None

    def test_missing_path(self):
        line = "ID 256 gen 100 cgen 50 top level 5 uuid aaa-bbb"
        assert _parse_subvol_line(line) is None

    def test_missing_id(self):
        line = "gen 100 cgen 50 top level 5 path rootfs"
        assert _parse_subvol_line(line) is None

    def test_no_cgen_falls_back_to_gen(self):
        line = (
            "ID 256 gen 100 top level 5 "
            "parent_uuid - received_uuid - "
            "uuid aaa-bbb "
            "path rootfs"
        )
        r = _parse_subvol_line(line)
        assert r is not None
        # Without cgen, ogen key should not exist, caller falls back to gen
        assert "ogen" not in r or r.get("ogen") == r.get("gen")


class TestExtentRegex:
    def test_standard_filefrag_line(self):
        line = "   0:        0..       7:    1234567..   1234574:          8:   last,eof"
        m = _EXTENT_RE.match(line)
        assert m is not None
        assert m.group(1) == "0"
        assert m.group(2) == "7"
        assert m.group(3) == "1234567"
        assert m.group(4) == "1234574"

    def test_no_match_header(self):
        line = " ext:     logical_offset:        physical_offset: length:   expected: flags:"
        assert _EXTENT_RE.match(line) is None

    def test_no_match_filename(self):
        line = "Filesystem type is: 9123683e"
        assert _EXTENT_RE.match(line) is None
