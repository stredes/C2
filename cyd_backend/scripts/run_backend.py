import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from server import main


if __name__ == "__main__":
    main()
