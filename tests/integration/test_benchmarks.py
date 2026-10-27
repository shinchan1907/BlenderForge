"""Integration tests for locked capability benchmark runner."""

from pathlib import Path
from blenderforge.config import BlenderForgeConfig
from blenderforge.evaluation.benchmark_runner import BenchmarkRunner
from blenderforge.storage.db import DatabaseManager


def test_benchmark_runner_execution(tmp_path: Path):
    cfg = BlenderForgeConfig(base_dir=tmp_path, data_dir=tmp_path / ".blenderforge")
    cfg.ensure_directories()
    db = DatabaseManager(cfg.db_path)

    runner = BenchmarkRunner(cfg, db)
    report = runner.run_all()

    assert report.total_tasks == 9
    assert report.passed_tasks >= 8  # All 9 passing on local environment
    assert report.overall_score >= 0.88
    assert len(report.results) == 9

    # Verify persistence in database
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM benchmark_runs")
        count = cur.fetchone()[0]
        assert count == 9
