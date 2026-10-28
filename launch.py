import sys
import traceback
from pathlib import Path

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        from openingroutes.worker import work

        try:
            work(Path(sys.argv[2]), sys.argv[3])
        except Exception:
            log_path = Path(sys.argv[2]) / "logs" / f"{sys.argv[3]}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log:
                traceback.print_exc(file=log)
            raise SystemExit(1) from None
    else:
        from openingroutes.desktop import main

        main()
