from datetime import datetime, timedelta, timezone
import json

import pytest

from app.services.deploy_locks import DeployLockConflict, _lock_key, acquire_deploy_lock


def test_deploy_lock_writes_metadata_and_releases(tmp_path):
    lock_root = tmp_path / "locks"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    with acquire_deploy_lock(
        lock_root=lock_root,
        plan_path=str(plan_path),
        workload_name="brand-funnels-test",
        job_id="job-1",
        org_id="org-1",
        user_id="user-1",
    ) as lock:
        assert lock.path.exists()
        metadata = json.loads((lock.path / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["lockVersion"] == 1
        assert metadata["planPath"] == str(plan_path.resolve())
        assert metadata["workloadName"] == "brand-funnels-test"
        assert metadata["jobId"] == "job-1"
        assert metadata["orgId"] == "org-1"
        assert metadata["userId"] == "user-1"

    assert not lock.path.exists()


def test_deploy_lock_rejects_concurrent_same_workload(tmp_path):
    lock_root = tmp_path / "locks"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")
    lock_dir = lock_root / f"{_lock_key(plan_path=str(plan_path), workload_name='brand-funnels-test')}.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "metadata.json").write_text(
        json.dumps(
            {
                "lockVersion": 1,
                "planPath": str(plan_path.resolve()),
                "workloadName": "brand-funnels-test",
                "jobId": "job-1",
                "acquiredAt": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DeployLockConflict, match="Deploy lock is already held"):
        with acquire_deploy_lock(
            lock_root=lock_root,
            plan_path=str(plan_path),
            workload_name="brand-funnels-test",
            job_id="job-2",
            org_id="org-1",
            user_id="user-2",
        ):
            pass


def test_deploy_lock_allows_reentrant_same_context(tmp_path):
    lock_root = tmp_path / "locks"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    with acquire_deploy_lock(
        lock_root=lock_root,
        plan_path=str(plan_path),
        workload_name="brand-funnels-test",
        job_id="job-1",
        org_id="org-1",
        user_id="user-1",
    ) as outer:
        with acquire_deploy_lock(
            lock_root=lock_root,
            plan_path=str(plan_path),
            workload_name="brand-funnels-test",
            job_id="job-1",
            org_id="org-1",
            user_id="user-1",
        ) as inner:
            assert inner.reentrant is True
            assert inner.path == outer.path


def test_deploy_lock_reports_stale_lock_without_removing_it(tmp_path):
    lock_root = tmp_path / "locks"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    lock_dir = lock_root / f"{_lock_key(plan_path=str(plan_path), workload_name='brand-funnels-test')}.lock"
    lock_dir.mkdir(parents=True)
    stale_time = datetime.now(timezone.utc) - timedelta(hours=8)
    (lock_dir / "metadata.json").write_text(
        json.dumps(
            {
                "lockVersion": 1,
                "planPath": str(plan_path.resolve()),
                "workloadName": "brand-funnels-test",
                "jobId": "stale-job",
                "acquiredAt": stale_time.isoformat(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DeployLockConflict, match="operator must inspect and remove it explicitly"):
        with acquire_deploy_lock(
            lock_root=lock_root,
            plan_path=str(plan_path),
            workload_name="brand-funnels-test",
            job_id="job-2",
            org_id="org-1",
            user_id="user-2",
        ):
            pass

    assert lock_dir.exists()
