import argparse
import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from .config import Settings
from .sync import run_forever, run_inspect, run_once, run_random_test


def main() -> None:
    parser = argparse.ArgumentParser(description="PhotoPrism <-> Mistral AI enrichment sync")
    parser.add_argument("--once", action="store_true", help="Run a single sync pass and exit")
    parser.add_argument(
        "--dry-run", action="store_true", help="Log intended changes without writing them"
    )
    parser.add_argument(
        "--random",
        action="store_true",
        help="Analyse one random photo and print the result, for testing the setup",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="With --random: actually save the analysis result to PhotoPrism",
    )
    parser.add_argument(
        "--inspect",
        metavar="UID",
        help="Print the raw PhotoPrism JSON for a photo UID and exit, for debugging field names",
    )
    args = parser.parse_args()

    load_dotenv()

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_file = os.environ.get("LOG_FILE")
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3))

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )

    settings = Settings.from_env()
    if args.dry_run:
        settings.dry_run = True

    if args.inspect:
        run_inspect(settings, args.inspect)
    elif args.random:
        run_random_test(settings, write=args.write)
    elif args.once:
        run_once(settings)
    else:
        run_forever(settings)


if __name__ == "__main__":
    main()
