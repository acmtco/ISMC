"""Приём кадров с камеры (`live`) или из папки (`replay`).

Режим переключается переменной окружения `HG_MODE`, не правкой кода.
Каркас CLI. Логика приёма не реализована.
"""
import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-id", required=True)
    parser.parse_args()
    mode = os.environ.get("HG_MODE", "replay")
    raise NotImplementedError(f"приём кадров в режиме {mode!r} ещё не реализован")


if __name__ == "__main__":
    main()
