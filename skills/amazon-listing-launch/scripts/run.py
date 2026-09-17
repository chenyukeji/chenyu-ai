from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from amazon_product_os.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["launch", *sys.argv[1:]]))

