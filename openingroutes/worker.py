import sys
from pathlib import Path

from .extract import extract_demo
from .store import Store


def work(root, job_id):
    store = Store(root)
    job = store.all("jobs")[job_id]

    def progress(stage):
        job.update(status="parsing", stage=stage)
        store.put("jobs", job_id, job)

    try:
        match = extract_demo(Path(root) / "uploads" / f"{job_id}.dem", job["source"], store, progress)
        job.update(status="complete", stage="complete", match_id=match["id"], error=None)
    except Exception as error:
        job.update(status="failed", error=f"{type(error).__name__}: Demo could not be parsed")
        raise
    finally:
        store.put("jobs", job_id, job)


if __name__ == "__main__":
    work(Path(sys.argv[1]), sys.argv[2])
