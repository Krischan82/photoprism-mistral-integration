import argparse
import logging
import os

from dotenv import load_dotenv

from .config import Settings
from .sync import run_forever, run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="PhotoPrism <-> Mistral AI enrichment sync")
    parser.add_argument("--once", action="store_true", help="Run a single sync pass and exit")
    parser.add_argument(
        "--dry-run", action="store_true", help="Log intended changes without writing them"
    )
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings.from_env()
    if args.dry_run:
        settings.dry_run = True

    if args.once:
        run_once(settings)
    else:
        run_forever(settings)


if __name__ == "__main__":
    main()
