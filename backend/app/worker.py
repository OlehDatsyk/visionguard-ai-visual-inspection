"""Standalone worker: python -m app.worker. Use with RUN_WORKER_IN_API=false and shared object storage."""
import logging
import signal

from app.services.jobs import Worker


def main() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    worker = Worker()
    signal.signal(signal.SIGTERM, lambda *_: worker.stop())
    signal.signal(signal.SIGINT, lambda *_: worker.stop())
    worker.start()
    while worker.is_alive():
        worker.join(timeout=1)


if __name__ == "__main__":
    main()
