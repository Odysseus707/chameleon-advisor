"""The read-only / writable split that makes the package installable."""
import os

import pytest

from chi_edge_bench import paths


def test_data_lives_inside_the_package():
    """If DATA ever escapes the package, the wheel stops carrying it."""
    import chi_edge_bench
    pkg = os.path.dirname(os.path.abspath(chi_edge_bench.__file__))
    assert str(paths.DATA).startswith(pkg)


@pytest.mark.parametrize("getter,pattern,count", [
    (paths.items_dir, "*.yaml", 134),
    (paths.snapshots_dir, "*.json", 7),
    (paths.grounding_dir, "A*.md", 6),
    (paths.extractions_dir, "*.yaml", 6),
])
def test_shipped_data_is_complete(getter, pattern, count):
    assert getter().is_dir(), f"{getter.__name__} missing"
    assert len(list(getter().glob(pattern))) == count


def test_capability_table_ships():
    """checks.py grades every capability claim against this file."""
    assert paths.capability_table().is_file()


def test_default_snapshot_ships():
    assert paths.default_snapshot().is_file()


def test_baselines_ship():
    csvs = sorted(p.name for p in paths.baselines_dir().glob("*.csv"))
    assert csvs == ["isolation_scores.csv", "tejas_scores.csv"]


class TestWorkspaceResolution:
    """Order is flag -> env -> marker -> default, and each must win over the next."""

    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        monkeypatch.delenv("CHI_BENCH_WORKSPACE", raising=False)
        paths.set_workspace(None)
        yield
        paths.set_workspace(None)

    def test_default_when_nothing_identifies_one(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert paths.workspace() == tmp_path / paths.DEFAULT_WORKSPACE_NAME
        assert "default" in paths.workspace_source()

    def test_marker_beats_default(self, tmp_path, monkeypatch):
        (tmp_path / paths.MARKER).write_text("")
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)          # found by walking up
        assert paths.workspace() == tmp_path

    def test_env_beats_marker(self, tmp_path, monkeypatch):
        (tmp_path / paths.MARKER).write_text("")
        monkeypatch.chdir(tmp_path)
        other = tmp_path / "elsewhere"
        monkeypatch.setenv("CHI_BENCH_WORKSPACE", str(other))
        assert paths.workspace() == other.resolve()

    def test_flag_beats_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHI_BENCH_WORKSPACE", str(tmp_path / "env"))
        pinned = tmp_path / "flag"
        paths.set_workspace(pinned)
        assert paths.workspace() == pinned.resolve()
        assert paths.workspace_source() == "--workspace"

    def test_reading_does_not_create_directories(self, tmp_path, monkeypatch):
        """A read-only command must not leave a directory behind."""
        monkeypatch.chdir(tmp_path)
        paths.workspace(), paths.runs_dir(), paths.exports_dir()
        assert list(tmp_path.iterdir()) == []
