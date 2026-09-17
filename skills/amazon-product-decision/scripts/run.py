from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from amazon_product_os.cli import main


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in {"profit", "compliance", "decision"}:
        print("Usage: run.py {profit|compliance|decision} ...", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))

