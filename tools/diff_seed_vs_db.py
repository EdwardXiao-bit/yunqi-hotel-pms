"""把 `sql/03_seed.sql` 里的 reservation 数据与当前演示库逐行比对（只读）。

用途：演示库被测试写入污染后，先看差在哪几行，再决定是否重灌种子。
用法：
    python tools/diff_seed_vs_db.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

SEED = ROOT / "sql" / "03_seed.sql"

ROW_RE = re.compile(
    r"\(\s*'(?P<no>R\d{11})'\s*,\s*(?P<customer_id>\d+)\s*,\s*(?P<room_id>\d+)\s*,\s*"
    r"DATE '(?P<check_in>\d{4}-\d{2}-\d{2})'\s*,\s*DATE '(?P<check_out>\d{4}-\d{2}-\d{2})'\s*,\s*"
    r"(?P<guests>\d+)\s*,\s*(?P<price_per_night>[\d.]+)\s*,\s*(?P<total_amount>[\d.]+)\s*,\s*"
    r"'(?P<status>[a-z_]+)'"
)


def parse_seed() -> dict[str, tuple]:
    text = SEED.read_text(encoding="utf-8")
    start = text.index("INSERT INTO reservation (")
    end = text.index(";", start)
    block = text[start:end]
    seed: dict[str, tuple] = {}
    for match in ROW_RE.finditer(block):
        seed[match["no"]] = (
            int(match["customer_id"]),
            int(match["room_id"]),
            match["check_in"],
            match["check_out"],
            int(match["guests"]),
            f"{float(match['price_per_night']):.2f}",
            f"{float(match['total_amount']):.2f}",
            match["status"],
        )
    return seed


def main() -> int:
    seed = parse_seed()
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT reservation_no, customer_id, room_id,
                   to_char(check_in_date, 'YYYY-MM-DD'), to_char(check_out_date, 'YYYY-MM-DD'),
                   guest_count, price_per_night, total_amount, status
            FROM reservation
            ORDER BY reservation_no
            """
        )
        db_rows = cur.fetchall()

    db = {
        row[0]: (
            row[1], row[2], row[3], row[4], row[5],
            f"{row[6]:.2f}", f"{row[7]:.2f}", row[8],
        )
        for row in db_rows
    }

    print(f"种子 {len(seed)} 行 / 库中 {len(db)} 行\n")

    missing = sorted(set(seed) - set(db))
    extra = sorted(set(db) - set(seed))
    if missing:
        print(f"库中缺少：{missing}")
    if extra:
        print(f"库中多出：{extra}")

    columns = ["customer_id", "room_id", "check_in", "check_out", "guest_count",
               "price_per_night", "total_amount", "status"]
    drifted = 0
    for no in sorted(set(seed) & set(db)):
        if seed[no] != db[no]:
            drifted += 1
            diffs = [
                f"{name}: 种子 {seed[no][i]!r} → 库中 {db[no][i]!r}"
                for i, name in enumerate(columns)
                if seed[no][i] != db[no][i]
            ]
            print(f"{no}: " + "；".join(diffs))

    print(f"\n差异行数：{drifted} / {len(seed)}")
    return 0 if drifted == 0 and not missing and not extra else 1


if __name__ == "__main__":
    raise SystemExit(main())
