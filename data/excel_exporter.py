"""
excel_exporter.py -- Multi-tab Excel workbook manager for 100-ticker live trading.

Creates and updates outputs/portfolio_trading_results.xlsx with:
- Master 'Portfolio Summary' tab displaying all 100 companies at a glance.
- Individual company tabs (e.g. NVDA, AAPL, MSFT) tracking tick-by-tick logs.
"""

import os
import logging
from typing import Dict, Any, List
import pandas as pd

logger = logging.getLogger(__name__)


class MultiTabExcelExporter:
    """
    Manages multi-tab Excel spreadsheet exporting for live multi-ticker trading.
    """

    def __init__(self, excel_path: str = None) -> None:
        if excel_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            outputs_dir = os.path.join(project_root, "outputs")
            os.makedirs(outputs_dir, exist_ok=True)
            excel_path = os.path.join(outputs_dir, "portfolio_trading_results.xlsx")
            
        self.excel_path = excel_path
        logger.info("MultiTabExcelExporter initialized -- path: %s", self.excel_path)

    def update_workbook(
        self,
        summary_rows: List[Dict[str, Any]],
        ticker_ticks: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        Update the Excel workbook with master summary rows and ticker tick updates.

        Parameters
        ----------
        summary_rows : List[Dict[str, Any]]
            List of dicts representing each ticker's current status for 'Portfolio Summary'.
        ticker_ticks : Dict[str, Dict[str, Any]]
            Mapping of ticker -> single tick data dictionary to append to that ticker's tab.
        """
        try:
            # 1. Prepare Portfolio Summary DataFrame
            summary_df = pd.DataFrame(summary_rows)
            if not summary_df.empty:
                cols_order = [
                    "Ticker", "Price ($)", "Signal", "Confidence",
                    "Reasons", "Position", "Unrealized P&L ($)", "Last Updated"
                ]
                # Ensure all columns exist
                for c in cols_order:
                    if c not in summary_df.columns:
                        summary_df[c] = ""
                summary_df = summary_df[cols_order]

            # 2. Read existing tabs if workbook exists
            existing_sheets = {}
            if os.path.exists(self.excel_path):
                try:
                    xls = pd.ExcelFile(self.excel_path, engine="openpyxl")
                    for sheet_name in xls.sheet_names:
                        if sheet_name != "Portfolio Summary":
                            existing_sheets[sheet_name] = pd.read_excel(
                                xls, sheet_name=sheet_name, engine="openpyxl"
                            )
                except Exception as ex:
                    logger.warning("Could not read existing workbook tabs: %s", ex)

            # 3. Append new tick data to each ticker's sheet DataFrame
            for ticker, tick in ticker_ticks.items():
                clean_sheet_name = str(ticker)[:30]  # Excel tab names max 31 chars
                row_data = {
                    "Timestamp": tick.get("time", ""),
                    "Price ($)": round(tick.get("price", 0.0), 2),
                    "RSI_14": round(tick.get("rsi", 50.0), 2),
                    "MACD": round(tick.get("macd", 0.0), 4),
                    "Signal": tick.get("signal", "SKIP"),
                    "Confidence": round(tick.get("confidence", 0.0), 2),
                    "Position": tick.get("pos_str", "No position"),
                    "PnL ($)": round(tick.get("pnl", 0.0), 2),
                }
                new_row_df = pd.DataFrame([row_data])

                if clean_sheet_name in existing_sheets and not existing_sheets[clean_sheet_name].empty:
                    updated_df = pd.concat([existing_sheets[clean_sheet_name], new_row_df], ignore_index=True)
                else:
                    updated_df = new_row_df

                existing_sheets[clean_sheet_name] = updated_df

            # 4. Write all sheets back using ExcelWriter
            with pd.ExcelWriter(self.excel_path, engine="openpyxl") as writer:
                # Master Portfolio Summary as 1st sheet
                if not summary_df.empty:
                    summary_df.to_excel(writer, sheet_name="Portfolio Summary", index=False)

                # Write individual company tabs
                for sheet_name, df_sheet in existing_sheets.items():
                    # Keep recent ~100 rows per sheet for compact file size
                    df_to_save = df_sheet.tail(100)
                    df_to_save.to_excel(writer, sheet_name=sheet_name, index=False)

            logger.info("Updated Excel workbook %s successfully.", self.excel_path)

        except Exception as e:
            logger.error("Failed to update Excel workbook: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("  MultiTabExcelExporter Diagnostic Test")
    print("=" * 60)

    exporter = MultiTabExcelExporter()
    
    dummy_summary = [
        {"Ticker": "NVDA", "Price ($)": 220.50, "Signal": "BUY", "Confidence": 0.75, "Reasons": "MACD bullish", "Position": "Holding 66sh", "Unrealized P&L ($)": -350.0, "Last Updated": "2026-08-11 00:20:00"},
        {"Ticker": "AAPL", "Price ($)": 235.10, "Signal": "SKIP", "Confidence": 0.00, "Reasons": "RSI neutral", "Position": "No position", "Unrealized P&L ($)": 0.0, "Last Updated": "2026-08-11 00:20:00"},
        {"Ticker": "MSFT", "Price ($)": 445.80, "Signal": "BUY", "Confidence": 0.80, "Reasons": "RSI oversold", "Position": "No position", "Unrealized P&L ($)": 0.0, "Last Updated": "2026-08-11 00:20:00"},
    ]

    dummy_ticks = {
        "NVDA": {"time": "2026-08-11 00:20:00", "price": 220.50, "rsi": 58.5, "macd": 3.2, "signal": "BUY", "confidence": 0.75, "pos_str": "Holding 66sh", "pnl": -350.0},
        "AAPL": {"time": "2026-08-11 00:20:00", "price": 235.10, "rsi": 50.0, "macd": 0.1, "signal": "SKIP", "confidence": 0.00, "pos_str": "No position", "pnl": 0.0},
        "MSFT": {"time": "2026-08-11 00:20:00", "price": 445.80, "rsi": 42.1, "macd": -1.5, "signal": "BUY", "confidence": 0.80, "pos_str": "No position", "pnl": 0.0},
    }

    exporter.update_workbook(dummy_summary, dummy_ticks)
    print("Excel test complete.")
    print("=" * 60)
