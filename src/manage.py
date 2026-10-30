#!/usr/bin/env python
"""Django manage.py —— 云栖酒店客房预订与入住管理系统。

运行：python src/manage.py runserver 8000
"""
import os
import sys
from pathlib import Path


def main() -> None:
    # src/ 加入 sys.path，保证 config / core 可导入
    base_dir = Path(__file__).resolve().parent
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "无法导入 Django，请确认已安装 Django 6.1（D:\\anaconda3\\python.exe -m pip install django）"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
