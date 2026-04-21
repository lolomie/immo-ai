#!/usr/bin/env python3
"""
Immo AI — Automation Polling Daemon

Usage:
  python scripts/run_automation.py          # continuous polling (default 60s interval)
  python scripts/run_automation.py --once   # single run, then exit
  python scripts/run_automation.py --interval 30  # poll every 30 seconds

The daemon:
  1. Reads pending rows from Google Sheets "Exposé-Inputs"
  2. Runs each through: Groq generation → Claude validation → Drive upload → Email
  3. Syncs new Termine to Google Calendar
  4. Sends 24h appointment reminders
  5. Logs every step to logs/pipeline/YYYY-MM-DD.jsonl
"""

import argparse
import logging
import os
import sys
import time

# Allow running from project root or scripts/ directory
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
sys.path.insert(0, _root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("automation")


def main() -> None:
    parser = argparse.ArgumentParser(description="Immo AI Automation Daemon")
    parser.add_argument("--once", action="store_true", help="Run once then exit")
    parser.add_argument("--interval", type=int, default=None, help="Poll interval in seconds")
    args = parser.parse_args()

    # Import here so config errors surface cleanly
    try:
        from src.config import AUTOMATION_POLL_INTERVAL
        from src.automation import poll_and_process
    except EnvironmentError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)
    except ImportError as e:
        logger.error("Import error (missing dependencies?): %s", e)
        logger.error("Run: pip install -r requirements.txt")
        sys.exit(1)

    interval = args.interval or AUTOMATION_POLL_INTERVAL

    logger.info("=" * 60)
    logger.info("Immo AI Automation Daemon starting")
    logger.info("Poll interval: %ds | Mode: %s", interval, "once" if args.once else "continuous")
    logger.info("=" * 60)

    if args.once:
        n = poll_and_process()
        logger.info("Single run complete — %d rows processed.", n)
        return

    # Continuous polling loop
    cycle = 0
    while True:
        cycle += 1
        logger.info("── Poll cycle #%d ──", cycle)
        try:
            n = poll_and_process()
            logger.info("Cycle #%d complete — %d rows processed.", cycle, n)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")
            break
        except Exception as e:
            logger.error("Unexpected error in cycle #%d: %s", cycle, e, exc_info=True)

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")
            break


if __name__ == "__main__":
    main()
