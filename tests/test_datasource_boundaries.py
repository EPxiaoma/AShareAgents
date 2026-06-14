"""Tests for the provider modules extracted from the A-share orchestrator."""

import importlib
import unittest
from unittest.mock import patch


class DatasourceBoundaryTests(unittest.TestCase):
    def test_provider_packages_are_importable(self):
        for package in (
            "baiduFinance",
            "clsFinance",
            "eastMoney",
            "mootdx",
            "sinaFinance",
            "tencentFinance",
            "tongHuaShun",
        ):
            module = importlib.import_module(f"AShareAgents.datasource.{package}")
            self.assertIsNotNone(module)

    def test_astock_uses_extracted_ticker_resolver(self):
        from AShareAgents.datasource.astock import a_stock

        a_stock._api_resolution_cache.clear()
        with patch.object(
            a_stock, "_resolve_eastmoney_stock_code", return_value="600519"
        ) as resolver:
            self.assertEqual(a_stock._resolve_by_api("贵州茅台"), "600519")
        resolver.assert_called_once_with("贵州茅台")

    def test_astock_uses_extracted_mootdx_bars(self):
        import pandas as pd

        from AShareAgents.datasource.astock import a_stock

        expected = pd.DataFrame(
            [{"Date": pd.Timestamp("2026-01-02"), "Open": 1, "High": 2,
              "Low": 1, "Close": 2, "Volume": 100}]
        )
        with (
            patch.object(a_stock.os.path, "exists", return_value=False),
            patch.object(a_stock.os, "makedirs"),
            patch.object(a_stock, "_get_mootdx_daily_bars", return_value=expected),
            patch.object(pd.DataFrame, "to_csv"),
        ):
            result = a_stock._load_ohlcv_astock("600000", "2026-01-03")
        self.assertEqual(result.iloc[0]["Close"], 2)


if __name__ == "__main__":
    unittest.main()
