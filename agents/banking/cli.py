import argparse
from typing import Optional

from .run import BankingInitializer
from .level3.run import main as level3_main


def cmd_level1(_: argparse.Namespace) -> None:
    bi = BankingInitializer()
    bi.initialize_level1_banking()
    bi.save_banks()


def cmd_level2(_: argparse.Namespace) -> None:
    bi = BankingInitializer()
    # Load existing Level 1 from files if present
    # then compute Level 2 only
    bi.initialize_level2_banking()
    bi.save_banks()


def cmd_level3(_: argparse.Namespace) -> None:
    level3_main()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="banking")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("level1")
    sp.set_defaults(func=cmd_level1)

    sp = sub.add_parser("level2")
    sp.set_defaults(func=cmd_level2)

    sp = sub.add_parser("level3")
    sp.set_defaults(func=cmd_level3)

    return p


def main(argv: Optional[list] = None) -> None:
    p = build_parser()
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()


