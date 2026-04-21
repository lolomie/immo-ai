#!/usr/bin/env python3
"""
Initialize Google Sheets: creates the three required tabs with correct headers.
Run once before starting the automation daemon.

Usage:
  python scripts/setup_sheets.py
"""

import logging
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        from src.sheets_client import ensure_sheet_headers
        from src.config import SHEETS_SPREADSHEET_ID
    except EnvironmentError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)

    if not SHEETS_SPREADSHEET_ID:
        logger.error("SHEETS_SPREADSHEET_ID not set in .env")
        sys.exit(1)

    logger.info("Connecting to spreadsheet: %s", SHEETS_SPREADSHEET_ID)

    try:
        ensure_sheet_headers()
        logger.info("✅ All tabs and headers are set up correctly.")
        logger.info("Next steps:")
        logger.info("  1. Add property data to the 'Exposé-Inputs' tab with status='pending'")
        logger.info("  2. Run: python scripts/run_automation.py --once")
    except Exception as e:
        logger.error("Setup failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
