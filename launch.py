import sys
from pathlib import Path

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        from openingroutes.worker import work

        work(Path(sys.argv[2]), sys.argv[3])
    else:
        from openingroutes.desktop import main

        main()
