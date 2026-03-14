"""Tests for btrfs_file_history/scanner.py — transition logic."""

import os
import stat
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from btrfs_file_history.btrfs import Subvolume, ExtentInfo
from btrfs_file_history.scanner import (
    FileState,
    FileTransition,
    FileHistory,
    _compute_transitions,
    _detect_modification,
    find_shared_extents,
)


def _sv(name: str, uuid: str, ogen: int = 0) -> Subvolume:
    return Subvolume(
        subvol_id=ogen + 256,
        gen=ogen,
        ogen=ogen,
        top_level=5,
        path=name,
        uuid=uuid,
        parent_uuid=None,
        received_uuid=None,
    )


def _state(sv: Subvolume, exists: bool, size: int = 0,
           mtime: float = 0.0, checksum: str = None,
           mode: int = None) -> FileState:
    if mode is None and exists:
        mode = stat.S_IFREG | 0o644
    return FileState(
        subvolume=sv,
        exists=exists,
        size=size if exists else None,
        mtime=mtime if exists else None,
        checksum=checksum,
        mode=mode,
    )


class TestComputeTransitions:
    def test_single_creation(self):
        sv1 = _sv("snap1", "u1", 1)
        states = [_state(sv1, True, size=100, mtime=1.0)]
        trans = _compute_transitions(states, False)
        assert len(trans) == 1
        assert trans[0].change_type == "created"

    def test_creation_then_unchanged(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        states = [
            _state(sv1, True, size=100, mtime=1.0),
            _state(sv2, True, size=100, mtime=1.0),
        ]
        trans = _compute_transitions(states, False)
        assert len(trans) == 2
        assert trans[0].change_type == "created"
        assert trans[1].change_type == "unchanged"

    def test_creation_then_modification(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        states = [
            _state(sv1, True, size=100, mtime=1.0),
            _state(sv2, True, size=200, mtime=2.0),
        ]
        trans = _compute_transitions(states, False)
        assert trans[1].change_type == "modified"

    def test_creation_then_deletion(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        states = [
            _state(sv1, True, size=100, mtime=1.0),
            _state(sv2, False),
        ]
        trans = _compute_transitions(states, False)
        assert trans[1].change_type == "deleted"

    def test_nonexistent_then_created(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        states = [
            _state(sv1, False),
            _state(sv2, True, size=50, mtime=1.0),
        ]
        trans = _compute_transitions(states, False)
        assert len(trans) == 1
        assert trans[0].change_type == "created"
        assert trans[0].curr.subvolume.uuid == "u2"

    def test_all_nonexistent(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        states = [_state(sv1, False), _state(sv2, False)]
        trans = _compute_transitions(states, False)
        assert len(trans) == 0

    def test_delete_then_recreate(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        sv3 = _sv("snap3", "u3", 3)
        states = [
            _state(sv1, True, size=100, mtime=1.0),
            _state(sv2, False),
            _state(sv3, True, size=50, mtime=3.0),
        ]
        trans = _compute_transitions(states, False)
        assert len(trans) == 3
        assert trans[0].change_type == "created"
        assert trans[1].change_type == "deleted"
        assert trans[2].change_type == "created"

    def test_consecutive_nonexistent_skipped(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        sv3 = _sv("snap3", "u3", 3)
        sv4 = _sv("snap4", "u4", 4)
        states = [
            _state(sv1, True, size=100, mtime=1.0),
            _state(sv2, False),
            _state(sv3, False),
            _state(sv4, True, size=100, mtime=4.0),
        ]
        trans = _compute_transitions(states, False)
        assert len(trans) == 3
        assert trans[0].change_type == "created"
        assert trans[1].change_type == "deleted"
        assert trans[2].change_type == "created"


class TestDetectModification:
    def test_size_change(self):
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0)
        new = _state(sv, True, size=200, mtime=1.0)
        assert _detect_modification(old, new, False) == "modified"

    def test_mtime_change_no_checksum(self):
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0)
        new = _state(sv, True, size=100, mtime=2.0)
        assert _detect_modification(old, new, False) == "modified"

    def test_mtime_change_same_checksum(self):
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0, checksum="aaa")
        new = _state(sv, True, size=100, mtime=2.0, checksum="aaa")
        assert _detect_modification(old, new, True) == "unchanged"

    def test_mtime_change_different_checksum(self):
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0, checksum="aaa")
        new = _state(sv, True, size=100, mtime=2.0, checksum="bbb")
        assert _detect_modification(old, new, True) == "modified"

    def test_same_everything(self):
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0)
        new = _state(sv, True, size=100, mtime=1.0)
        assert _detect_modification(old, new, False) == "unchanged"

    def test_type_changed_dir_to_file(self):
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=0, mtime=1.0,
                     mode=stat.S_IFDIR | 0o755)
        new = _state(sv, True, size=100, mtime=2.0,
                     mode=stat.S_IFREG | 0o644)
        assert _detect_modification(old, new, False) == "type_changed"

    def test_checksum_differs_same_size_mtime(self):
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0, checksum="aaa")
        new = _state(sv, True, size=100, mtime=1.0, checksum="bbb")
        assert _detect_modification(old, new, True) == "modified"


class TestFileHistory:
    def test_created_in(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        s1 = _state(sv1, False)
        s2 = _state(sv2, True, size=100, mtime=1.0)
        trans = _compute_transitions([s1, s2], False)
        h = FileHistory(relative_path="test.txt", states=[s1, s2],
                        transitions=trans)
        assert h.created_in is not None
        assert h.created_in.uuid == "u2"

    def test_modified_in(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        sv3 = _sv("snap3", "u3", 3)
        states = [
            _state(sv1, True, size=100, mtime=1.0),
            _state(sv2, True, size=100, mtime=1.0),
            _state(sv3, True, size=200, mtime=3.0),
        ]
        trans = _compute_transitions(states, False)
        h = FileHistory(relative_path="test.txt", states=states,
                        transitions=trans)
        modified = h.modified_in
        assert len(modified) == 1
        assert modified[0].uuid == "u3"

    def test_no_creation(self):
        h = FileHistory(relative_path="test.txt", states=[],
                        transitions=[])
        assert h.created_in is None
        assert h.modified_in == []


class TestFindSharedExtents:
    def test_shared_physical_offset(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        ext = ExtentInfo(logical_offset=0, physical_offset=1000,
                         length=8, flags="")
        s1 = _state(sv1, True, size=100, mtime=1.0)
        s1.extents = [ext]
        s2 = _state(sv2, True, size=100, mtime=1.0)
        s2.extents = [ExtentInfo(logical_offset=0, physical_offset=1000,
                                 length=8, flags="")]
        h = FileHistory(relative_path="test", states=[s1, s2],
                        transitions=[])
        shared = find_shared_extents(h)
        assert 1000 in shared
        assert len(shared[1000]) == 2

    def test_no_shared(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        s1 = _state(sv1, True, size=100, mtime=1.0)
        s1.extents = [ExtentInfo(0, 1000, 8, "")]
        s2 = _state(sv2, True, size=100, mtime=1.0)
        s2.extents = [ExtentInfo(0, 2000, 8, "")]
        h = FileHistory(relative_path="test", states=[s1, s2],
                        transitions=[])
        shared = find_shared_extents(h)
        assert len(shared) == 0

    def test_inline_extents_skipped(self):
        sv1 = _sv("snap1", "u1", 1)
        sv2 = _sv("snap2", "u2", 2)
        s1 = _state(sv1, True, size=10, mtime=1.0)
        s1.extents = [ExtentInfo(0, 500, 1, "inline")]
        s2 = _state(sv2, True, size=10, mtime=1.0)
        s2.extents = [ExtentInfo(0, 500, 1, "inline")]
        h = FileHistory(relative_path="test", states=[s1, s2],
                        transitions=[])
        shared = find_shared_extents(h)
        assert len(shared) == 0

    def test_zero_offset_zero_length_skipped(self):
        sv1 = _sv("snap1", "u1", 1)
        s1 = _state(sv1, True, size=0, mtime=1.0)
        s1.extents = [ExtentInfo(0, 0, 0, "")]
        h = FileHistory(relative_path="test", states=[s1],
                        transitions=[])
        shared = find_shared_extents(h)
        assert len(shared) == 0


class TestRendererHelpers:
    """Test pure helper functions from renderer.py."""

    def test_human_size_bytes(self):
        from btrfs_file_history.renderer import _human_size
        assert _human_size(0) == "0B"
        assert _human_size(512) == "512B"
        assert _human_size(1023) == "1023B"

    def test_human_size_kib(self):
        from btrfs_file_history.renderer import _human_size
        assert _human_size(1024) == "1.0KiB"
        assert _human_size(1536) == "1.5KiB"

    def test_human_size_mib(self):
        from btrfs_file_history.renderer import _human_size
        assert _human_size(1048576) == "1.0MiB"

    def test_human_size_none(self):
        from btrfs_file_history.renderer import _human_size
        assert _human_size(None) == "—"

    def test_truncate(self):
        from btrfs_file_history.renderer import _truncate
        assert _truncate("short", 10) == "short"
        assert _truncate("exactly10!", 10) == "exactly10!"
        assert len(_truncate("this is too long", 10)) == 10
        assert _truncate("this is too long", 10).endswith("…")

    def test_dot_id(self):
        from btrfs_file_history.renderer import _dot_id
        assert _dot_id("aaa-bbb-ccc") == "aaa_bbb_ccc"
        assert _dot_id("no_dashes") == "no_dashes"

    def test_dot_escape(self):
        from btrfs_file_history.renderer import _dot_escape
        assert _dot_escape('hello "world"') == 'hello \\"world\\"'
        assert _dot_escape("no quotes") == "no quotes"

    def test_color_enabled(self):
        from btrfs_file_history.renderer import _color, _C
        result = _color("text", _C.RED, enabled=True)
        assert result.startswith("\033[")
        assert "text" in result

    def test_color_disabled(self):
        from btrfs_file_history.renderer import _color, _C
        result = _color("text", _C.RED, enabled=False)
        assert result == "text"


class TestDiffer:
    def test_size_delta(self):
        from btrfs_file_history.differ import diff_states
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0)
        new = _state(sv, True, size=150, mtime=2.0)
        result = diff_states(old, new)
        assert result.size_delta == 50

    def test_content_identical_with_checksum(self):
        from btrfs_file_history.differ import diff_states
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0, checksum="abc")
        new = _state(sv, True, size=100, mtime=2.0, checksum="abc")
        result = diff_states(old, new)
        assert result.content_identical is True

    def test_content_different(self):
        from btrfs_file_history.differ import diff_states
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0, checksum="abc")
        new = _state(sv, True, size=100, mtime=2.0, checksum="xyz")
        result = diff_states(old, new)
        assert result.content_identical is False

    def test_no_checksum_not_identical(self):
        from btrfs_file_history.differ import diff_states
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0)
        new = _state(sv, True, size=100, mtime=2.0)
        result = diff_states(old, new)
        assert result.content_identical is False

    def test_shared_extents(self):
        from btrfs_file_history.differ import diff_states
        sv = _sv("s", "u", 1)
        old = _state(sv, True, size=100, mtime=1.0)
        old.extents = [ExtentInfo(0, 1000, 8, ""), ExtentInfo(8, 2000, 8, "")]
        new = _state(sv, True, size=100, mtime=2.0)
        new.extents = [ExtentInfo(0, 1000, 8, ""), ExtentInfo(8, 3000, 8, "")]
        result = diff_states(old, new)
        assert result.shared_extent_count == 1
        assert result.old_extent_count == 2
        assert result.new_extent_count == 2
