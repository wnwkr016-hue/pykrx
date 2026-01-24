import pytest
from pykrx import stock
import pandas as pd
import numpy as np
# pylint: disable-all
# flake8: noqa


class TestEtfTickerList:
    @pytest.mark.cassette("etf/ticker_list.yaml")
    def test_ticker_list(self, use_cassette):
        tickers = stock.get_etf_ticker_list()
        assert isinstance(tickers, list)
        assert len(tickers) > 0

    @pytest.mark.cassette("etf/ticker_list_20210104.yaml")
    def test_ticker_list_with_a_businessday(self, use_cassette):
        tickers = stock.get_etf_ticker_list("20210104")
        assert isinstance(tickers, list)
        assert len(tickers) > 0

    @pytest.mark.cassette("etf/ticker_list_20210103.yaml")
    def test_ticker_list_with_a_holiday(self, use_cassette):
        tickers = stock.get_etf_ticker_list("20210103")
        assert isinstance(tickers, list)
        assert len(tickers) > 0


class TestEtnTickerList:
    @pytest.mark.cassette("etf/etn_ticker_list.yaml")
    def test_ticker_list(self, use_cassette):
        tickers = stock.get_etn_ticker_list()
        assert isinstance(tickers, list)
        assert len(tickers) > 0

    @pytest.mark.cassette("etf/etn_ticker_list_20210104.yaml")
    def test_ticker_list_with_a_businessday(self, use_cassette):
        tickers = stock.get_etn_ticker_list("20210104")
        assert isinstance(tickers, list)
        assert len(tickers) > 0

    @pytest.mark.cassette("etf/etn_ticker_list_20210103.yaml")
    def test_ticker_list_with_a_holiday(self, use_cassette):
        tickers = stock.get_etn_ticker_list("20210103")
        assert isinstance(tickers, list)
        assert len(tickers) > 0


class TestElwTickerList:
    @pytest.mark.cassette("etf/elw_ticker_list.yaml")
    def test_ticker_list(self, use_cassette):
        tickers = stock.get_elw_ticker_list()
        assert isinstance(tickers, list)
        assert len(tickers) > 0

    @pytest.mark.cassette("etf/elw_ticker_list_20210104.yaml")
    def test_ticker_list_with_a_businessday(self, use_cassette):
        tickers = stock.get_elw_ticker_list("20210104")
        assert isinstance(tickers, list)

    @pytest.mark.cassette("etf/elw_ticker_list_20210103.yaml")
    def test_ticker_list_with_a_holiday(self, use_cassette):
        tickers = stock.get_elw_ticker_list("20210103")
        assert isinstance(tickers, list)


class TestEtfOhlcvByDate:
    @pytest.mark.cassette("etf/ohlcv_by_date_069500_20210104_20210108.yaml")
    def test_with_business_day(self, use_cassette):
        df = stock.get_etf_ohlcv_by_date("20210104", "20210108", "069500")
        temp = df.iloc[0:5, 0] == np.array(
            [40615.17, 41230.17, 40835.69, 41709.04, 43651.13]
        )
        assert temp.sum() == 5
        assert isinstance(df.index, pd.core.indexes.datetimes.DatetimeIndex)
        assert isinstance(df.index[0], pd._libs.tslibs.timestamps.Timestamp)
        assert df.index[0] < df.index[-1]

    @pytest.mark.cassette("etf/ohlcv_by_date_069500_20210103_20210108.yaml")
    def test_with_holiday_0(self, use_cassette):
        df = stock.get_etf_ohlcv_by_date("20210103", "20210108", "069500")
        temp = df.iloc[0:5, 0] == np.array(
            [40615.17, 41230.17, 40835.69, 41709.04, 43651.13]
        )
        assert temp.sum() == 5
        assert isinstance(df.index, pd.core.indexes.datetimes.DatetimeIndex)
        assert isinstance(df.index[0], pd._libs.tslibs.timestamps.Timestamp)
        assert df.index[0] < df.index[-1]

    @pytest.mark.cassette("etf/ohlcv_by_date_069500_20210103_20210109.yaml")
    def test_with_holiday_1(self, use_cassette):
        df = stock.get_etf_ohlcv_by_date("20210103", "20210109", "069500")
        temp = df.iloc[0:5, 0] == np.array(
            [40615.17, 41230.17, 40835.69, 41709.04, 43651.13]
        )
        assert temp.sum() == 5
        assert isinstance(df.index, pd.core.indexes.datetimes.DatetimeIndex)
        assert isinstance(df.index[0], pd._libs.tslibs.timestamps.Timestamp)
        assert df.index[0] < df.index[-1]

    @pytest.mark.cassette("etf/ohlcv_by_date_069500_20200101_20200531_freq_m.yaml")
    def test_with_freq(self, use_cassette):
        df = stock.get_etf_ohlcv_by_date("20200101", "20200531", "069500", freq="m")
        temp = df.iloc[0:5, 0] == np.array(
            [29522.38, 28938.98, 27458.11, 23105.09, 25106.00]
        )
        assert temp.sum() == 5
        assert isinstance(df.index, pd.core.indexes.datetimes.DatetimeIndex)
        assert isinstance(df.index[0], pd._libs.tslibs.timestamps.Timestamp)
        assert df.index[0] < df.index[-1]


class TestEtfOhlcvByTicker:
    @pytest.mark.cassette("etf/ohlcv_by_ticker_20210325.yaml")
    def test_with_business_day(self, use_cassette):
        df = stock.get_etf_ohlcv_by_ticker("20210325")
        temp = df.iloc[0:5, 0] == np.array(
            [41887.33, 10969.41, 46182.13, 4344.07, 9145.45]
        )
        assert temp.sum() == 5

    @pytest.mark.cassette("etf/ohlcv_by_ticker_20210321.yaml")
    def test_with_holiday(self, use_cassette):
        df = stock.get_etf_ohlcv_by_ticker("20210321")
        assert df.empty


class TestEtfPriceChange:
    @pytest.mark.cassette("etf/price_change_20210325_20210402.yaml")
    def test_with_business_day(self, use_cassette):
        df = stock.get_etf_price_change_by_ticker("20210325", "20210402")
        temp = df.iloc[0:5, 2] == np.array([1690, 330, 3965, -365, 290])
        assert temp.sum() == 5

    @pytest.mark.cassette("etf/price_change_20210321_20210325.yaml")
    def test_with_holiday_0(self, use_cassette):
        df = stock.get_etf_price_change_by_ticker("20210321", "20210325")
        temp = df.iloc[0:5, 2] == np.array([-390, -75, -950, 70, -85])
        assert temp.sum() == 5

    @pytest.mark.cassette("etf/price_change_20210321_20210321.yaml")
    def test_with_holiday_1(self, use_cassette):
        df = stock.get_etf_price_change_by_ticker("20210321", "20210321")
        assert df.empty


class TestEtfPdf:
    @pytest.mark.cassette("etf/pdf_152100_20210402.yaml")
    def test_with_business_day(self, use_cassette):
        df = stock.get_etf_portfolio_deposit_file("152100", "20210402")
        temp = df.iloc[0:5, 0] == np.array([8140.0, 968.0, 218.0, 79.0, 89.0])
        assert temp.sum() == 5

    @pytest.mark.cassette("etf/pdf_114800_20210402.yaml")
    def test_with_negative_value(self, use_cassette):
        df = stock.get_etf_portfolio_deposit_file("114800", "20210402")
        assert df.iloc[1, 0] == pytest.approx(-3.58)


class TestEtfTradingvolumeValue:
    @pytest.mark.cassette("etf/trading_volume_20220415_20220422.yaml")
    def test_investor_in_businessday(self, use_cassette):
        df = stock.get_etf_trading_volume_and_value("20220415", "20220422")
        temp = df.iloc[0:4, 0] == np.array([375220036, 15784738, 14415013, 6795002])
        assert temp.sum() == 4

    @pytest.mark.cassette("etf/trading_volume_20220415_20220422_amount.yaml")
    def test_volume_with_businessday(self, use_cassette):
        df = stock.get_etf_trading_volume_and_value(
            "20220415", "20220422", "거래대금", "순매수"
        )
        temp = df.iloc[0:5, 0] == np.array(
            [25346770535, -168362290065, -36298873785, -235935697655, -33385835805]
        )
        assert temp.sum() == 5

    @pytest.mark.cassette("etf/trading_volume_0069M0_20260116_20260123.yaml")
    def test_indivisual_investor_in_businessday(self, use_cassette):
        df = stock.get_etf_trading_volume_and_value("20260116", "20260123", "0069M0")
        temp = df.iloc[0] == np.array(
            [1227682, 879808, -347874, 15193534642, 10895889652, -4297644990]
        )
        assert temp.sum() == 6

    @pytest.mark.cassette("etf/trading_volume_0069M0_20260116_20260123_amount.yaml")
    def test_indivisual_volume_with_businessday(self, use_cassette):
        df = stock.get_etf_trading_volume_and_value(
            "20260116", "20260123", "0069M0", "거래대금", "순매수"
        )
        temp = df.iloc[0:5, 0] == np.array(
            [-5925058, -1610960700, -228752248, -938151339, -402496746]
        )
        assert temp.sum() == 5
