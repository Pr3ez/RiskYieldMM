import pandas as pd
import numpy as np
import time
import joblib
import pandas_ta as ta
import ta  # Make sure pandas-ta is installed
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import logging
import requests
#import talib  
from pybit.unified_trading import HTTP
from pybit.exceptions import FailedRequestError, InvalidRequestError
import dateparser
import traceback
import math
from typing import Dict, List, Optional
from pathlib import Path
import json
import os
from catboost import CatBoost
from catboost import CatBoostClassifier






#### Config functions
# Global tracker for available margin
available_margin_tracker = None
pair = "BTCUSDT"

# Configure Logging
logging.basicConfig(level=logging.INFO, filename=f'bybit_bot_{pair}.log',
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Initialize Bybit client
client = HTTP(
    api_key="5Z37Ko6xX1mPSIctRt",
    api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
    testnet=False  # Set to True if using the testnet
)


feature_cols = [
    # Base features
    "RSI_14", "MACD_Line", "ATR_14", "SMA_50",
    "Bollinger_Upper", "Bollinger_Lower", "Price_Volatility",
    "CCI_14", "Momentum", "KC_Upper", "KC_Lower", "KC_Middle",

    # RSI_14 lags
    "RSI_14_lag1", "RSI_14_lag2", "RSI_14_lag3", "RSI_14_lag4", "RSI_14_lag5", "RSI_14_lag6",

    # MACD lags
    "MACD_lag1", "MACD_lag2", "MACD_lag3", "MACD_lag4", "MACD_lag5", "MACD_lag6",

    # ATR_14 lags
    "ATR_14_lag1", "ATR_14_lag2", "ATR_14_lag3", "ATR_14_lag4", "ATR_14_lag5", "ATR_14_lag6",

    # SMA_50 lags
    "SMA_50_lag1", "SMA_50_lag2", "SMA_50_lag3", "SMA_50_lag4", "SMA_50_lag5", "SMA_50_lag6",

    # Bollinger_Upper lags
    "Bollinger_Upper_lag1", "Bollinger_Upper_lag2", "Bollinger_Upper_lag3", "Bollinger_Upper_lag4", "Bollinger_Upper_lag5", "Bollinger_Upper_lag6",

    # Bollinger_Lower lags
    "Bollinger_Lower_lag1", "Bollinger_Lower_lag2", "Bollinger_Lower_lag3", "Bollinger_Lower_lag4", "Bollinger_Lower_lag5", "Bollinger_Lower_lag6",

    # Price_Volatility lags
    "Price_Volatility_lag1", "Price_Volatility_lag2", "Price_Volatility_lag3", "Price_Volatility_lag4", "Price_Volatility_lag5", "Price_Volatility_lag6",

    # CCI_14 lags
    "CCI_14_lag1", "CCI_14_lag2", "CCI_14_lag3", "CCI_14_lag4", "CCI_14_lag5", "CCI_14_lag6",

    # Momentum lags
    "Momentum_lag1", "Momentum_lag2", "Momentum_lag3", "Momentum_lag4", "Momentum_lag5", "Momentum_lag6",

    # KC_Upper lags
    "KC_Upper_lag1", "KC_Upper_lag2", "KC_Upper_lag3", "KC_Upper_lag4", "KC_Upper_lag5", "KC_Upper_lag6",

    # KC_Lower lags
    "KC_Lower_lag1", "KC_Lower_lag2", "KC_Lower_lag3", "KC_Lower_lag4", "KC_Lower_lag5", "KC_Lower_lag6",

    # KC_Middle lags
    "KC_Middle_lag1", "KC_Middle_lag2", "KC_Middle_lag3", "KC_Middle_lag4", "KC_Middle_lag5", "KC_Middle_lag6"
]

# ============================
# Helper Functions
# ============================
#First helper functions
def get_current_orders(symbol, testnet=False):
    """
    Fetches and prints all active (limit/market) orders for the specified symbol on Bybit.

    Args:
        symbol (str): Trading pair (e.g., 'pair').
        testnet (bool): If True, use Bybit testnet.

    Returns:
        list: A list of open orders for the specified symbol.
    """
    session = HTTP(testnet=testnet)
    symbol = symbol.upper()

    # Determine product category
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
    elif symbol.endswith("USDT") or symbol.endswith("USDC"):
        category = "linear"
    else:
        category = "spot"

    try:
        # Query active orders (v5 endpoint /v5/order/list)
        resp = session.get(
            "/v5/order/list",
            params={"category": category, "symbol": symbol, "limit": 100}
        )
        orders = resp.get("result", {}).get("list", [])

        if not orders:
            print(f"No open orders found for {symbol}.")
            return []

        print(f"Current Open Orders for {symbol}:")
        for order in orders:
            print(
                f"- Order ID: {order.get('orderId')}, Side: {order.get('side')}, "
                f"Price: {order.get('price')}, Quantity: {order.get('qty')}, "
                f"Type: {order.get('orderType')}, Status: {order.get('orderStatus')}"
            )
        return orders

    except (FailedRequestError, InvalidRequestError) as e:
        print(f"Bybit API error fetching current orders for {symbol}: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error in get_current_orders for {symbol}: {e}")
        return []

def cancel_all_sl_tp_orders(symbol, testnet=False):
    """
    Cancels all active stop-loss and take-profit reduce-only conditional orders for a given symbol on Bybit.
    """
    session = HTTP(
        api_key="5Z37Ko6xX1mPSIctRt",
        api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
        testnet=testnet
    )
    symbol = symbol.upper()

    # Detect market category
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
    elif symbol.endswith("USDT") or symbol.endswith("USDC"):
        category = "linear"
    else:
        category = "spot"

    try:
        resp = session.get_open_orders(category=category, symbol=symbol, limit=100)
        orders = resp.get("result", {}).get("list", [])

        for order in orders:
            order_id = order.get("orderId")
            is_reduce_only = order.get("reduceOnly", False)
            is_conditional = "triggerPrice" in order and order.get("orderType") == "Market"

            if is_reduce_only and is_conditional and order_id:
                try:
                    print(f"Canceling reduce-only conditional order: {order_id}")
                    session.cancel_order(category=category, symbol=symbol, orderId=order_id)
                except Exception as e:
                    print(f"Failed to cancel order {order_id}: {e}")

    except Exception as e:
        print(f"Error fetching or canceling orders: {e}")

def has_active_position(symbol, testnet=False):
    """
    Checks if there is an active (non-zero) position for the specified trading pair on Bybit.

    Args:
        symbol (str): Trading pair (e.g., 'pair').
        testnet (bool): If True, use Bybit testnet.

    Returns:
        bool: True if an active position exists, False otherwise.
    """
    # Initialize the session with API keys
    session = HTTP(
        api_key="5Z37Ko6xX1mPSIctRt",
        api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
        testnet=testnet
    )
    symbol = symbol.upper()

    # Determine product category and settleCoin
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
        settle_coin = "BTC"  # Default settle coin for inverse contracts
    elif symbol.endswith("USDT") or symbol.endswith("USDC"):
        category = "linear"
        settle_coin = "USDT"  # Default settle coin for linear contracts
    else:
        category = "spot"
        settle_coin = None  # Spot trading does not use settleCoin

    try:
        # Fetch current positions for the symbol
        resp = session.get_positions(category=category, settleCoin=settle_coin)
        positions = resp.get('result', {}).get('list', [])

        for position in positions:
            size = float(position.get('size', 0))
            if abs(size) > 0:
                print(f"Active position detected for {symbol}")
                return True
        return False

    except Exception as e:
        print(f"Unexpected error checking active positions for {symbol}: {e}")
        return False

def check_open_positions(symbol, testnet=False):
    """
    Checks if there is an open position for the given symbol on Bybit.

    Args:
        symbol (str): Trading pair (e.g. 'pair').
        testnet (bool): If True, use Bybit testnet.

    Returns:
        bool: True if an open position exists, False otherwise.
    """
    session = HTTP(testnet=testnet)
    symbol = symbol.upper()

    # Determine product category and settleCoin
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
        settle_coin = "BTC"  # Default settle coin for inverse contracts
    elif symbol.endswith("USDT") or symbol.endswith("USDC"):
        category = "linear"
        settle_coin = "USDT"  # Default settle coin for linear contracts
    else:
        category = "spot"
        settle_coin = None  # Spot trading does not use settleCoin

    try:
        # Prepare parameters for the API request
        params = {"category": category, "symbol": symbol}
        if settle_coin:
            params["settleCoin"] = settle_coin

        # Fetch current positions
        resp = session.get("/v5/position/list", params=params)
        positions = resp.get('result', {}).get('list', [])

        for position in positions:
            size = float(position.get('size', 0))
            if position.get('symbol') == symbol and size != 0:
                print(f"Open position detected for {symbol}")
                return True
        return False

    except (FailedRequestError, InvalidRequestError) as e:
        print(f"Bybit API error checking open positions: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error checking open positions: {e}")
        return False

def fetch_trade_history(symbol, lookback_days=14, max_retries=3):
    """
    Fetches the trade history for a given symbol from Bybit and calculates trade statistics.
    Handles cases where no trade history is found by returning default values.

    Args:
        symbol (str): Trading pair (e.g., 'pair').
        lookback_days (int): Number of days to look back for trade history.
        max_retries (int): Maximum number of retries for API calls.

    Returns:
        dict: A dictionary containing trade statistics (win_prob, loss_prob, win_ratio, loss_ratio).
    """
    session = HTTP(
        api_key="5Z37Ko6xX1mPSIctRt",
        api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
        testnet=False  # Set to True if using the testnet
    )
    now = int(time.time() * 1000)
    start_time = now - (lookback_days * 24 * 60 * 60 * 1000)
    cursor = None
    all_trades = []

    for attempt in range(max_retries):
        try:
            while True:
                response = session.get_executions(
                    category="linear",
                    symbol=symbol,
                    settleCoin="USDT",  # Add this if required
                    start=start_time,
                    limit=1000,
                    cursor=cursor
                )
                if response.get("ret_code") != 0:
                    print(f"API Error: {response.get('ret_msg')}")
                    return {"win_prob": 0.5, "loss_prob": 0.5, "win_ratio": 1.5, "loss_ratio": 1.0}

                data = response.get("result", {})
                trades = data.get("list", [])

                if not trades:
                    break

                all_trades.extend(trades)
                cursor = data.get("nextPageCursor")
                if not cursor:
                    break

            if not all_trades:
                print(f"No trade history found for {symbol} in the last {lookback_days} days.")
                return {"win_prob": 0.5, "loss_prob": 0.5, "win_ratio": 1.5, "loss_ratio": 1.0}

            # Process trades
            win_trades = []
            loss_trades = []

            for trade in all_trades:
                pnl = float(trade.get("execProfit", 0))
                if pnl > 0:
                    win_trades.append(pnl)
                elif pnl < 0:
                    loss_trades.append(pnl)

            win_count = len(win_trades)
            loss_count = len(loss_trades)
            total_trades = win_count + loss_count

            if total_trades == 0:
                print("No trades to calculate win/loss ratios.")
                return {"win_prob": 0.5, "loss_prob": 0.5, "win_ratio": 1.5, "loss_ratio": 1.0}

            win_prob = win_count / total_trades
            loss_prob = loss_count / total_trades

            max_cap = 100000
            win_trades = [min(pnl, max_cap) for pnl in win_trades]
            loss_trades = [min(pnl, max_cap) for pnl in loss_trades]

            win_ratio = sum(win_trades) / win_count if win_count > 0 else 1.5
            loss_ratio = abs(sum(loss_trades) / loss_count) if loss_count > 0 else 1.0

            print(f"Total Trades: {total_trades}, Wins: {win_count}, Losses: {loss_count}")
            print(f"Win Prob: {win_prob:.2f}, Loss Prob: {loss_prob:.2f}")
            print(f"Win Ratio: {win_ratio:.2f}, Loss Ratio: {loss_ratio:.2f}")

            return {"win_prob": win_prob, "loss_prob": loss_prob, "win_ratio": win_ratio, "loss_ratio": loss_ratio}

        except Exception as e:
            print(f"Unexpected error while fetching trade history: {e}")
            return {"win_prob": 0.5, "loss_prob": 0.5, "win_ratio": 1.5, "loss_ratio": 1.0}
        
def round_quantity_to_step_size(quantity, step_size):
    # Convert to Decimal
    quantity_dec = Decimal(str(quantity))
    step_size_dec = Decimal(str(step_size))

    # Determine the number of decimal places allowed by the step size
    step_size_str = f"{step_size:.16f}".rstrip('0')
    if '.' in step_size_str:
        decimals = len(step_size_str.split('.')[1])
    else:
        decimals = 0

    # Calculate how many whole steps fit into the quantity
    steps = (quantity_dec / step_size_dec).quantize(Decimal('1'), rounding=ROUND_DOWN)
    # Multiply back by step size and quantize to the correct decimal places
    rounded_quantity = (steps * step_size_dec).quantize(Decimal('1e-{}'.format(decimals)), rounding=ROUND_DOWN)
    return float(rounded_quantity)


def get_tick_size(symbol=pair, testnet=False):
    from pybit.unified_trading import HTTP
    from pybit.exceptions import FailedRequestError, InvalidRequestError

    session = HTTP(testnet=testnet)
    symbol = symbol.upper()

    # Determine product category
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
    elif symbol.endswith("USDT") or symbol.endswith("USDC"):
        category = "linear"
    else:
        category = "spot"

    try:
        # Query instrument info for the symbol
        resp = session.get_instruments_info(category=category, symbol=symbol)
        result = resp.get("result", {})
        data_list = result.get("list", [])
        if not data_list:
            print(f"No data found for symbol: {symbol}")
            return None

        info = data_list[0]
        price_filter = info.get("priceFilter", {})
        tick_size = price_filter.get("tickSize")
        return float(tick_size) if tick_size is not None else None

    except (FailedRequestError, InvalidRequestError) as e:
        print(f"Bybit API error fetching tick size for {symbol}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching tick size for {symbol}: {e}")
        return None

def round_price(price, symbol):
    """
    Rounds the price to match Bybit's tick size for the given symbol.

    Args:
        price (float): The price to round.
        symbol (str): Trading pair symbol (e.g., pair).

    Returns:
        float: The rounded price.
    """
    tick_size = get_tick_size(symbol)
    if tick_size and tick_size > 0:
        tick_precision = int(abs(np.log10(tick_size)))
        return round(price, tick_precision)
    else:
        print("Unable to fetch tick size, returning original price.")
        return price

def create_volume_increased_buy(df, window=1):
    """
    Creates a 'volume_increased_buy' column indicating if volume has increased compared to the previous period.

    Args:
        df (pd.DataFrame): The DataFrame containing market data.
        window (int): The number of periods to look back for comparison.

    Returns:
        pd.DataFrame: DataFrame with the new 'volume_increased_buy' column.
    """
    df['volume_increased_buy'] = df['volume'].diff(window) > 0
    df['volume_increased_buy'] = df['volume_increased_buy'].fillna(False)
    return df

def calculate_support_resistance(df, window=14):
    try:
        df["Support"] = df["low"].rolling(window=window).min()
        df["Resistance"] = df["high"].rolling(window=window).max()
        print("Support and Resistance calculated successfully.")
    except Exception as e:
        print(f"Error calculating support and resistance: {e}")
    return df

def calculate_keltner_channels(df, ema_window=20, atr_window=14, multiplier=2):
    """
    Calculates Keltner Channels (Upper, Middle, Lower) and adds them to the DataFrame.

    Args:
        df (pd.DataFrame): DataFrame containing 'high', 'low', 'close' columns.
        ema_window (int): Window size for the EMA (middle line).
        atr_window (int): Window size for the ATR.
        multiplier (int): Multiplier for the ATR to calculate upper and lower bands.

    Returns:
        pd.DataFrame: DataFrame with added Keltner Channel columns.
    """
    try:
        # Ensure required columns exist
        required_columns = ['high', 'low', 'close']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns for Keltner Channels: {missing_columns}")

        # Calculate the middle line (EMA of close price)
        ema = ta.trend.EMAIndicator(close=df["close"], window=ema_window)
        df["KC_Middle"] = ema.ema_indicator()

        # Calculate the ATR
        atr = ta.volatility.AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=atr_window)
        df["ATR"] = atr.average_true_range()

        # Calculate the upper and lower bands
        df["KC_Upper"] = df["KC_Middle"] + (multiplier * df["ATR"])
        df["KC_Lower"] = df["KC_Middle"] - (multiplier * df["ATR"])

        # Debugging: Log the last few rows of the calculated columns
        logging.debug(f"Keltner Channels calculated successfully. Last rows:\n{df[['KC_Upper', 'KC_Middle', 'KC_Lower']].tail()}")

        return df
    except ValueError as ve:
        logging.error(f"ValueError in calculate_keltner_channels: {ve}")
        return df
    except Exception as e:
        logging.error(f"Error calculating Keltner Channels: {e}", exc_info=True)
        return df

def calculate_additional_indicators(df):
    """
    Calculates additional technical indicators for confirmation.
    """
    try:
        # Verify required columns
        required_columns = ['high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"Missing required column: '{col}'")
        logger.info("All required columns are present in the DataFrame.")
        logger.debug(df[['high', 'low', 'close', 'volume']].head())  # Debugging

        # Check for NaN or infinite values
        if df[['high', 'low', 'close', 'volume']].isnull().any().any():
            raise ValueError("Data contains NaN values in required columns.")
        if np.isinf(df[['high', 'low', 'close', 'volume']]).any().any():
            raise ValueError("Data contains infinite values in required columns.")

        # On-Balance Volume
        obv = ta.volume.OnBalanceVolumeIndicator(close=df["close"], volume=df["volume"])
        df["OBV"] = obv.on_balance_volume()
        logger.info("OBV calculated.")

        # Stochastic %K and %D
        stoch = ta.momentum.StochasticOscillator(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=14,
            smooth_window=3
        )
        df["Stochastic_%K"] = stoch.stoch()
        df["Stochastic_%D"] = stoch.stoch_signal()
        logger.info("Stochastic %K and %D calculated.")

        # Williams %R
        williams = ta.momentum.WilliamsRIndicator(high=df["high"], low=df["low"], close=df["close"], lbp=14)
        df["Williams_%R"] = williams.williams_r()
        logger.info("Williams %R calculated.")

        # Ensure CCI column is present (we assume CCI_14 is already calculated)
        if "CCI_14" in df.columns:
            df["CCI"] = df["CCI_14"]
        else:
            # Calculate CCI_14 if not available
            cci = ta.trend.CCIIndicator(high=df["high"], low=df["low"], close=df["close"], window=20)
            df["CCI_14"] = cci.cci()
            df["CCI"] = df["CCI_14"]
        logger.info("CCI confirmed.")

        # ADX, DI+, DI-, and ADX Moving Average
        adx_window = 14
        adx_ma_window = 10  # Define the moving average window for ADX smoothing

        logger.info(f"DataFrame length before ADX check: {len(df)}")
        if len(df) >= adx_window + 1:
            adx = ta.trend.ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=adx_window)
            df["DI+"] = adx.adx_pos()
            df["DI-"] = adx.adx_neg()
            df["ADX"] = adx.adx()

            # Calculate ADX Moving Average
            df["ADX_MA"] = df["ADX"].rolling(window=adx_ma_window, min_periods=1).mean()
            logger.info("ADX, DI+, DI-, and ADX Moving Average calculated.")
        else:
            logger.warning(f"Not enough data points ({len(df)}) for ADX calculations. Skipping ADX.")
            df["DI+"] = np.nan
            df["DI-"] = np.nan
            df["ADX"] = np.nan
            df["ADX_MA"] = np.nan

        # Volume Oscillator
        fastperiod = 12
        slowperiod = 26
        signalperiod = 9

        df['MA_fast'] = df['volume'].rolling(window=fastperiod, min_periods=1).mean()
        df['MA_slow'] = df['volume'].rolling(window=slowperiod, min_periods=1).mean()

        df['Volume_Oscillator'] = ((df['MA_fast'] - df['MA_slow']) / df['MA_slow']) * 100
        df['Volume_Oscillator_Signal'] = df['Volume_Oscillator'].ewm(span=signalperiod, adjust=False).mean()

        df.drop(['MA_fast', 'MA_slow'], axis=1, inplace=True)

        logger.info("Volume Oscillator and Signal Line calculated.")
        logger.info("Additional indicators calculated successfully.")
        return df

    except Exception as e:
        logger.error(f"Error calculating additional indicators: {e}")
        return df

def compute_rsi_low_high(
    df: pd.DataFrame,
    window: int = 21,
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
    rsi_low_name: str = "RSI_LOW",
    rsi_high_name: str = "RSI_HIGH",
) -> pd.DataFrame:
    """
    Given a DataFrame with price columns, returns two new Series:
      - `rsi_low_name`: RSI(window) treating each bar's low as its closing price for that bar's gain/loss
      - `rsi_high_name`: RSI(window) treating each bar's high similarly

    This preserves all prior EMA smoothing on true closes, and only replaces the single bar's gain/loss.
    """
    # 1) baseline deltas and EMA-smoothed avg_gain / avg_loss on true closes
    price = df[close_col]
    delta      = price.diff()
    gain       = delta.where(delta > 0, 0.0)
    loss       = -delta.where(delta < 0, 0.0)

    # EMA alpha = 1/window
    avg_gain  = gain.ewm(alpha=1/window, min_periods=window).mean()
    avg_loss  = loss.ewm(alpha=1/window, min_periods=window).mean()

    # 2) prepare output arrays
    rsi_low  = pd.Series(index=df.index, dtype=float)
    rsi_high = pd.Series(index=df.index, dtype=float)

    # 3) loop from first valid index
    start = avg_gain.first_valid_index()
    if start is None:
        # not enough data
        df[rsi_low_name]  = rsi_low
        df[rsi_high_name] = rsi_high
        return df

    start_idx = df.index.get_loc(start)

    for idx in range(start_idx, len(df)):
        prev_close = df[close_col].iat[idx-1]

        # — LOW substitution —
        g_low = max(0.0, df[low_col].iat[idx]  - prev_close)
        l_low = max(0.0, prev_close            - df[low_col].iat[idx])
        ag_low = ((window - 1) * avg_gain.iat[idx-1] + g_low) / window
        al_low = ((window - 1) * avg_loss.iat[idx-1] + l_low) / window
        rs_low = ag_low / al_low if al_low != 0 else float("inf")
        rsi_low.iat[idx] = 100 - (100 / (1 + rs_low))

        # — HIGH substitution —
        g_high = max(0.0, df[high_col].iat[idx] - prev_close)
        l_high = max(0.0, prev_close           - df[high_col].iat[idx])
        ag_high = ((window - 1) * avg_gain.iat[idx-1] + g_high) / window
        al_high = ((window - 1) * avg_loss.iat[idx-1] + l_high) / window
        rs_high = ag_high / al_high if al_high != 0 else float("inf")
        rsi_high.iat[idx] = 100 - (100 / (1 + rs_high))

    # 4) attach back to df
    df[rsi_low_name]  = rsi_low
    df[rsi_high_name] = rsi_high
    return df



def calculate_time_to_million(
    symbol: str = pair,
    starting_balance: float = 100.0,
    target_balance: float = 1_000_000.0,
    lookback_days: int = 14,
    testnet: bool = False
) -> float:
    """
    Estimates days to reach target balance based on historical trade PnL from Bybit.

    Args:
        symbol (str): Trading pair (e.g., 'BTCUSDT').
        starting_balance (float): Current wallet balance.
        target_balance (float): Goal balance (default $1M).
        lookback_days (int): Days to look back for trade history.
        testnet (bool): Use Bybit testnet if True.

    Returns:
        float: Estimated days to reach target, or None on error.
    """
    session = HTTP(api_key="5Z37Ko6xX1mPSIctRt", api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV", testnet=testnet)
    now_ms = int(time.time() * 1000)
    start_time = now_ms - lookback_days * 24 * 60 * 60 * 1000
    cursor = None
    all_trades = []

    try:
        # Paginate through execution list
        while True:
            params = {
                "category": "linear",
                "symbol": symbol,
                "start": start_time,
                "limit": 1000
            }
            if cursor:
                params["cursor"] = cursor

            # Use the correct method to fetch executions
            resp = session.get_executions(**params)
            result = resp.get("result", {})
            trades = result.get("list", [])
            if not trades:
                break

            all_trades.extend(trades)
            cursor = result.get("nextPageCursor")
            if not cursor:
                break

        if not all_trades:
            print(f"No trade history found for {symbol} in the last {lookback_days} days.")
            return None

        # Calculate total PnL and trade count
        total_pnl = 0.0
        trade_count = 0
        for trade in all_trades:
            pnl = float(trade.get("execProfit", 0))
            total_pnl += pnl
            trade_count += 1

        if trade_count == 0:
            print("No trades found to calculate profits.")
            return None

        # Average profit/trade and trades/day
        avg_profit_per_trade = total_pnl / trade_count
        avg_trades_per_day = trade_count / lookback_days
        avg_daily_profit = avg_profit_per_trade * avg_trades_per_day

        if avg_daily_profit <= 0:
            print("Average daily profit is zero or negative. Cannot estimate time to target.")
            return None

        remaining = target_balance - starting_balance
        estimated_days = remaining / avg_daily_profit
        print(f"Estimated Time to Reach {target_balance}: {estimated_days:.2f} days")
        return estimated_days

    except (FailedRequestError, InvalidRequestError) as e:
        print(f"Bybit API error in calculate_time_to_million: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in calculate_time_to_million: {e}")
        return None

def check_no_open_orders_and_positions(symbol, category="linear"):
    """
    Checks if there are no open orders or active positions for ANY symbol other than the given one.

    Args:
        symbol (str): The current trading pair (e.g., 'BTCUSDT').
        category (str): Market category ('linear', 'inverse', etc.).

    Returns:
        bool: True if no open orders or active positions exist for other pairs, False otherwise.
    """
    try:
        print(f"[DEBUG] Checking for open orders or active positions (excluding: {symbol})")

        settle_coin = "USDT" if category == "linear" else "BTC" if category == "inverse" else None
        if not settle_coin:
            raise ValueError(f"Unsupported category: {category}")

        # Step 1: Check open orders for all symbols under this settleCoin
        open_orders_response = client.get_open_orders(category=category, settleCoin=settle_coin)
        open_orders = open_orders_response.get("result", {}).get("list", [])

        print(f"[DEBUG] Open orders response: {open_orders_response}")
        for order in open_orders:
            if order.get("symbol") != symbol:
                print(f"[INFO] Open order found for other symbol: {order.get('symbol')}")
                return False

        print("[INFO] No open orders for other symbols found.")

        # Step 2: Check positions for all symbols under this settleCoin
        positions_response = client.get_positions(category=category, settleCoin=settle_coin)
        positions = positions_response.get("result", {}).get("list", [])

        print(f"[DEBUG] Positions response: {positions_response}")
        for position in positions:
            if position.get("symbol") != symbol and float(position.get("size", 0)) != 0:
                print(f"[INFO] Active position found for other symbol: {position.get('symbol')} with size {position.get('size')}")
                return False

        print("[INFO] No active positions for other symbols found.")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to check open orders or positions: {e}")
        return False




def monitor_order_fulfillment(symbol, category="linear"):
    """
    Monitors stop-loss and take-profit orders. Cancels the remaining order if one is fulfilled.
    
    Args:
        symbol (str): Trading pair symbol (e.g., pair).
        category (str): The category of the market (default is "linear").
    """
    try:
        # Fetch all open orders for the symbol
        open_orders_response = client.get_open_orders(category=category, symbol=symbol)
        open_orders = open_orders_response.get("result", {}).get("list", [])

        active_sl_tp_orders = [
            order for order in open_orders 
            if order["orderType"] in ["Stop", "TakeProfit", "StopMarket", "TakeProfitMarket"]
        ]

        if not active_sl_tp_orders:
            print(f"No active stop-loss or take-profit orders to monitor for {symbol}.")
            return

        print(f"Active SL/TP Orders for {symbol}:")
        for order in active_sl_tp_orders:
            print(f"Order ID: {order['orderId']}, Type: {order['orderType']}, Trigger Price: {order.get('triggerPrice')}")

        # Check if any of the SL/TP orders are filled
        for order in active_sl_tp_orders:
            order_status_response = client.get_order(category=category, symbol=symbol, orderId=order["orderId"])
            order_status = order_status_response.get("result", {})
            if order_status.get("orderStatus") == "Filled":
                print(f"Order {order['orderId']} ({order['orderType']}) fulfilled. Cancelling the remaining SL/TP orders.")

                # Cancel other SL/TP orders
                for remaining_order in active_sl_tp_orders:
                    if remaining_order["orderId"] != order["orderId"]:
                        try:
                            client.cancel_order(category=category, symbol=symbol, orderId=remaining_order["orderId"])
                            print(f"Cancelled remaining SL/TP order: {remaining_order['orderId']}")
                        except Exception as e:
                            print(f"Error cancelling order {remaining_order['orderId']}: {e}")
                break  # Stop monitoring after handling the filled order

    except Exception as e:
        print(f"Unexpected error in monitor_order_fulfillment for {symbol}: {e}")

def cancel_existing_entry_order(symbol):
    """
    Cancels all open orders for the specified symbol on Bybit.
    This is used when action is HOLD — we no longer care about specific order IDs.
    """
    try:
        print(f"[INFO] Attempting to cancel all open orders for {symbol}")

        open_orders_response = client.get_open_orders(
            category="linear",
            symbol=symbol
        )
        open_orders = open_orders_response.get("result", {}).get("list", [])

        if not open_orders:
            print(f"[INFO] No open orders found for {symbol}. Nothing to cancel.")
            return

        for order in open_orders:
            order_id = order.get("orderId")
            status = order.get("orderStatus", "UNKNOWN")
            print(f"[INFO] Cancelling order: {order_id} | status: {status} | qty: {order['qty']}")
            
            cancel_response = client.cancel_order(
                category="linear",
                symbol=symbol,
                orderId=order_id
            )
            if cancel_response.get("retCode") == 0:
                print(f"[SUCCESS] Cancelled order: {order_id}")
            else:
                print(f"[ERROR] Failed to cancel order: {order_id} | Reason: {cancel_response.get('retMsg')}")

        # Optional: Clear tracked entry order if it exists
        if order_tracker.get("entry_order") and order_tracker["entry_order"]["symbol"] == symbol:
            print(f"[INFO] Clearing tracked entry_order for symbol: {symbol}")
            order_tracker["entry_order"] = None

    except Exception as e:
        print(f"[ERROR] Exception while canceling orders for {symbol}: {e}")




def get_step_size(symbol):
    """
    Fetches the step size for the given symbol from Bybit's Unified Trading API.

    Args:
        symbol (str): Trading pair (e.g., pair).

    Returns:
        float: The step size for the given symbol.
    """
    try:
        # Fetch symbol info from Bybit
        response = client.get_instruments_info(
            category="linear",  # Use "linear", "inverse", or "option" depending on the market
            symbol=symbol
        )

        instruments = response.get("result", {}).get("list", [])
        if not instruments:
            raise ValueError(f"Symbol {symbol} not found in Bybit instruments info.")

        symbol_info = instruments[0]
        step_size = float(symbol_info["lotSizeFilter"]["qtyStep"])
        return step_size

    except Exception as e:
        print(f"Error fetching step size for {symbol} from Bybit: {e}")
        return None

# Function to close position
def close_position(symbol, action, quantity):
    """
    Closes an active position by executing a market order.

    Args:
        symbol (str): Trading pair symbol (e.g., pair).
        action (str): Action to close the position ("Buy" for closing a short, "Sell" for closing a long).
        quantity (float): Quantity of the position to close.
    """
    try:
        # Place a market order to close the position
        order = client.place_active_order(
            symbol=symbol,
            side=action,
            order_type="Market",
            qty=quantity,
            reduce_only=True  # Ensures this is only for closing the position
        )
        print(f"Position closed: {order}")
        return order
    except Exception as e:
        print(f"Error closing position for {symbol}: {e}")

def calculate_atr(data, period=14):
    """
    Calculates the Average True Range (ATR) for the given data.

    Args:
        data (pd.DataFrame): Market data with 'high', 'low', 'close' columns.
        period (int): Number of periods to calculate ATR.

    Returns:
        pd.Series: ATR values.
    """
    high_low = data['high'] - data['low']
    high_close_prev = np.abs(data['high'] - data['close'].shift())
    low_close_prev = np.abs(data['low'] - data['close'].shift())
    true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=1).mean()
    return atr

# ============================
# Fetching Functions
# ============================

# Fetching indicators
# Ensure this helper function is available for support/resistance calculations
def calculate_support_resistance(data):
    """
    Adds support and resistance levels to the DataFrame.
    """
    data['Support'] = data['low'].rolling(window=20).min()
    data['Resistance'] = data['high'].rolling(window=20).max()
    return data

def calculate_fibonacci_retracement(df):
    """
    Calculate Fibonacci retracement levels and add them to the DataFrame.
    """
    high = df['high'].max()
    low = df['low'].min()
    diff = high - low

    df['Fib_0.382'] = high - 0.382 * diff
    df['Fib_0.5'] = high - 0.5 * diff
    df['Fib_0.618'] = high - 0.618 * diff

    return df


def to_milliseconds(val):
    """
    Converts a relative time string (e.g., '30 days ago', '30 days ago UTC') or datetime to milliseconds since epoch.
    Returns the result as a string to avoid integer overflow.
    """
    try:
        logging.debug(f"Converting to milliseconds: {val}")
        if val is None:
            return None

        # If the value is already in milliseconds
        if isinstance(val, (int, float)) and 1e9 < val < 1e13:
            return str(int(val))

        # If the value is in seconds
        if isinstance(val, (int, float)) and val < 1e9:
            return str(int(val * 1000))

        # Handle relative time strings
        if isinstance(val, str):
            if "days ago" in val:
                days_ago = int(val.split(" ")[0])
                absolute_time = datetime.now(timezone.utc) - timedelta(days=days_ago)
                return str(int(absolute_time.timestamp() * 1000))
            elif "hours ago" in val:
                hours_ago = int(val.split(" ")[0])
                absolute_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
                return str(int(absolute_time.timestamp() * 1000))

        # Handle datetime strings
        timestamp = pd.to_datetime(val, utc=True).timestamp()
        if not (0 <= timestamp <= 1e12):
            raise ValueError(f"Invalid timestamp value: {timestamp}")
        return str(int(timestamp * 1000))

    except Exception as e:
        logging.error(f"Error converting value to milliseconds: {val}, Error: {e}")
        return None



def process_timestamp(val):
    """
    Processes a timestamp to ensure it fits within a valid range for Bybit's API.
    Converts the timestamp to milliseconds if necessary.

    Args:
        val: The input timestamp (can be in seconds, milliseconds, or a relative time string).

    Returns:
        str: The processed timestamp in milliseconds as a string.
    """
    try:
        logging.debug(f"Processing timestamp: {val}")
        if val is None:
            return None

        # If the value is already in milliseconds, ensure it's valid
        if isinstance(val, (int, float)) and 1e12 > val > 1e9:  # Likely in milliseconds
            return str(int(val))

        # If the value is in seconds, convert to milliseconds
        if isinstance(val, (int, float)) and val < 1e9:  # Likely in seconds
            return str(int(val * 1000))

        # If the value is a relative time string (e.g., '30 days ago UTC')
        if isinstance(val, str):
            return to_milliseconds(val)

        # Convert string or datetime to milliseconds
        timestamp = pd.to_datetime(val, utc=True).timestamp()
        if not (0 <= timestamp <= 1e12):  # Sanity check for valid timestamp range
            raise ValueError(f"Invalid timestamp value: {timestamp}")
        return str(int(timestamp * 1000))

    except Exception as e:
        logging.error(f"Error processing timestamp: {val}, Error: {e}")
        return None
    
def _get_vo_series(df: pd.DataFrame) -> pd.Series:
    """
    Return a *numeric* Series representing the Volume Oscillator.
    Falls back to 0 when no VO column is available.
    """
    for cand in ('Volume_Oscillator', 'VolumeOscillator', 'VO'):
        if cand in df.columns:
            return pd.to_numeric(df[cand], errors='coerce').fillna(0)
    # last resort – an all-zero Series keeps downstream code alive
    return pd.Series(0, index=df.index, dtype=float)

def add_indicator_flags(df: pd.DataFrame, tf: str, is_forming: bool) -> pd.DataFrame:
    """
    Compute symmetric bullish & bearish boolean flags in one batch
    (avoids pandas fragmentation warnings).
    """
    close_col, volume_col = "close", "volume"
    f = {}                                            # <- collect every flag here

    # ── Bollinger ───────────────────────────────────────────────────────────
    f["close_above_BB_upper"] = df[close_col] > df["BB_upper"]
    f["close_between_BB_upper_upper_middle"] = (
        (df[close_col] <= df["BB_upper"]) & (df[close_col] > df["BB_upper_middle"])
    )
    f["close_between_BB_upper_middle"] = (
        (df[close_col] <= df["BB_upper_middle"]) & (df[close_col] > df["BB_middle"])
    )
    f["close_between_BB_middle_lower_middle"] = (
        (df[close_col] <= df["BB_middle"]) & (df[close_col] > df["BB_lower_middle"])
    )
    f["close_between_BB_lower_middle_lower"] = (
        (df[close_col] <= df["BB_lower_middle"]) & (df[close_col] > df["BB_lower"])
    )
    f["close_below_BB_lower"] = df[close_col] <= df["BB_lower"]

    # ── Keltner ─────────────────────────────────────────────────────────────
    f["close_above_KC_upper"] = df[close_col] > df["KC_upper"]
    f["close_between_KC_upper_upper_middle"] = (
        (df[close_col] <= df["KC_upper"]) & (df[close_col] > df["KC_upper_middle"])
    )
    f["close_between_KC_upper_middle"] = (
        (df[close_col] <= df["KC_upper_middle"]) & (df[close_col] > df["KC_middle"])
    )
    f["close_between_KC_middle_lower_middle"] = (
        (df[close_col] <= df["KC_middle"]) & (df[close_col] > df["KC_lower_middle"])
    )
    f["close_between_KC_lower_middle_lower"] = (
        (df[close_col] <= df["KC_lower_middle"]) & (df[close_col] > df["KC_lower"])
    )
    f["close_below_KC_lower"] = df[close_col] <= df["KC_lower"]

    # ── Volume vs SMA ───────────────────────────────────────────────────────
    for period in (5, 20):
        sma = f"VOL_SMA_{period}"
        if sma in df.columns:
            f[f"volume_above_{sma}"] = df[volume_col] > df[sma]
            f[f"volume_below_{sma}"] = df[volume_col] < df[sma]

    # ── Momentum & ROC ──────────────────────────────────────────────────────
    df["VO"] = _get_vo_series(df)
    f["VO_positive"]       = df["VO"] > 0
    f["VO_negative"]       = df["VO"] < 0
    f["ROC_14_positive"]   = df["ROC_14"] > 0
    f["ROC_14_negative"]   = df["ROC_14"] < 0
    f["ROC_14_increasing"] = df["ROC_14"] > df["ROC_14"].shift(1)
    f["ROC_14_decreasing"] = df["ROC_14"] < df["ROC_14"].shift(1)

    # ── Support / Resistance ───────────────────────────────────────────────
    f["close_above_Support_20"] = df[close_col] > df["Support_20"]
    f["close_below_Support_20"] = df[close_col] < df["Support_20"]
    f["close_below_Resistance_20"] = df[close_col] < df["Resistance_20"]
    f["close_above_Resistance_20"] = df[close_col] > df["Resistance_20"]

    # ── RSI ────────────────────────────────────────────────────────────────
    for r in (9, 14, 21):
        col = f"RSI_{r}"
        f[f"{col}_oversold"]      = df[col] < 30
        f[f"{col}_overbought"]    = df[col] > 70
        f[f"{col}_cross_up_30"]   = (df[col] > 30) & (df[col].shift(1) <= 30)
        f[f"{col}_cross_down_30"] = (df[col] < 30) & (df[col].shift(1) >= 30)
        f[f"{col}_cross_down_70"] = (df[col] < 70) & (df[col].shift(1) >= 70)
        f[f"{col}_cross_up_70"]   = (df[col] > 70) & (df[col].shift(1) <= 70)

    # ── CCI / STOCH / WILLR ────────────────────────────────────────────────
    f["CCI_14_overbought"]     = df["CCI_14"] > 100
    f["CCI_14_oversold"]       = df["CCI_14"] < -100
    f["CCI_14_cross_up_-100"]  = (df["CCI_14"] > -100) & (df["CCI_14"].shift(1) <= -100)
    f["CCI_14_cross_down_-100"] = (df["CCI_14"] < -100) & (df["CCI_14"].shift(1) >= -100)
    f["CCI_14_cross_down_100"] = (df["CCI_14"] < 100)  & (df["CCI_14"].shift(1) >= 100)
    f["CCI_14_cross_up_100"]   = (df["CCI_14"] > 100)  & (df["CCI_14"].shift(1) <= 100)

    f["STOCH_K_overbought"] = df["STOCH_K"] > 80
    f["STOCH_K_oversold"]   = df["STOCH_K"] < 20
    f["STOCH_K_cross_up_D"] = (
        (df["STOCH_K"] > df["STOCH_D"]) & (df["STOCH_K"].shift(1) <= df["STOCH_D"].shift(1))
    )
    f["STOCH_K_cross_down_D"] = (
        (df["STOCH_K"] < df["STOCH_D"]) & (df["STOCH_K"].shift(1) >= df["STOCH_D"].shift(1))
    )

    f["WILLR_14_overbought"]     = df["WILLR_14"] > -20
    f["WILLR_14_oversold"]       = df["WILLR_14"] < -80
    f["WILLR_14_cross_up_-80"]   = (df["WILLR_14"] > -80) & (df["WILLR_14"].shift(1) <= -80)
    f["WILLR_14_cross_down_-80"] = (df["WILLR_14"] < -80) & (df["WILLR_14"].shift(1) >= -80)
    f["WILLR_14_cross_down_-20"] = (df["WILLR_14"] < -20) & (df["WILLR_14"].shift(1) >= -20)
    f["WILLR_14_cross_up_-20"]   = (df["WILLR_14"] > -20) & (df["WILLR_14"].shift(1) <= -20)

    # ── ADX / DI ───────────────────────────────────────────────────────────
    f["ADX_14_strong_trend"] = df["ADX_14"] > 25
    f["ADX_14_weak_trend"]   = df["ADX_14"] < 25

    f["PLUS_DI_above_MINUS_DI"] = df["PLUS_DI_14"] > df["MINUS_DI_14"]
    f["MINUS_DI_above_PLUS_DI"] = df["MINUS_DI_14"] > df["PLUS_DI_14"]

    f["PLUS_DI_cross_up_MINUS_DI"]   = (df["PLUS_DI_14"] > df["MINUS_DI_14"]) & (
                                        df["PLUS_DI_14"].shift(1) <= df["MINUS_DI_14"].shift(1))
    f["PLUS_DI_cross_down_MINUS_DI"] = (df["PLUS_DI_14"] < df["MINUS_DI_14"]) & (
                                        df["PLUS_DI_14"].shift(1) >= df["MINUS_DI_14"].shift(1))
    f["MINUS_DI_cross_up_PLUS_DI"]   = (df["MINUS_DI_14"] > df["PLUS_DI_14"]) & (
                                        df["MINUS_DI_14"].shift(1) <= df["PLUS_DI_14"].shift(1))
    f["MINUS_DI_cross_down_PLUS_DI"] = (df["MINUS_DI_14"] < df["PLUS_DI_14"]) & (
                                        df["MINUS_DI_14"].shift(1) >= df["PLUS_DI_14"].shift(1))

    # ── Moving-average relationships ───────────────────────────────────────
    for sma in (5, 20, 50, 200):
        f[f"close_above_SMA_{sma}"] = df[close_col] > df[f"SMA_{sma}"]
        f[f"close_below_SMA_{sma}"] = df[close_col] < df[f"SMA_{sma}"]
    for ema in (9, 20, 50, 200):
        f[f"close_above_EMA_{ema}"] = df[close_col] > df[f"EMA_{ema}"]
        f[f"close_below_EMA_{ema}"] = df[close_col] < df[f"EMA_{ema}"]

    # pairwise MA relationships
    f["EMA_9_above_EMA_21"]  = df["EMA_9"]  > df["EMA_21"]
    f["EMA_9_below_EMA_21"]  = df["EMA_9"]  < df["EMA_21"]
    f["EMA_20_above_EMA_50"] = df["EMA_20"] > df["EMA_50"]
    f["EMA_20_below_EMA_50"] = df["EMA_20"] < df["EMA_50"]
    f["SMA_20_above_SMA_50"] = df["SMA_20"] > df["SMA_50"]
    f["SMA_20_below_SMA_50"] = df["SMA_20"] < df["SMA_50"]

    f["EMA_9_cross_up_EMA_21"]    = (df["EMA_9"]  > df["EMA_21"]) & (df["EMA_9"].shift(1)  <= df["EMA_21"].shift(1))
    f["EMA_9_cross_down_EMA_21"]  = (df["EMA_9"]  < df["EMA_21"]) & (df["EMA_9"].shift(1)  >= df["EMA_21"].shift(1))
    f["EMA_20_cross_up_EMA_50"]   = (df["EMA_20"] > df["EMA_50"]) & (df["EMA_20"].shift(1) <= df["EMA_50"].shift(1))
    f["EMA_20_cross_down_EMA_50"] = (df["EMA_20"] < df["EMA_50"]) & (df["EMA_20"].shift(1) >= df["EMA_50"].shift(1))
    f["SMA_20_cross_up_SMA_50"]   = (df["SMA_20"] > df["SMA_50"]) & (df["SMA_20"].shift(1) <= df["SMA_50"].shift(1))
    f["SMA_20_cross_down_SMA_50"] = (df["SMA_20"] < df["SMA_50"]) & (df["SMA_20"].shift(1) >= df["SMA_50"].shift(1))

    # price crossing specific MA
    f["close_cross_up_SMA_20"]   = (df[close_col] > df["SMA_20"]) & (df[close_col].shift(1) <= df["SMA_20"].shift(1))
    f["close_cross_down_SMA_20"] = (df[close_col] < df["SMA_20"]) & (df[close_col].shift(1) >= df["SMA_20"].shift(1))
    f["close_cross_up_EMA_50"]   = (df[close_col] > df["EMA_50"]) & (df[close_col].shift(1) <= df["EMA_50"].shift(1))
    f["close_cross_down_EMA_50"] = (df[close_col] < df["EMA_50"]) & (df[close_col].shift(1) >= df["EMA_50"].shift(1))

    # ── MACD ────────────────────────────────────────────────────────────────
    f["MACD_positive"]         = df["MACD"] > 0
    f["MACD_negative"]         = df["MACD"] < 0
    f["MACD_hist_positive"]    = df["MACD_hist"] > 0
    f["MACD_hist_negative"]    = df["MACD_hist"] < 0
    f["MACD_above_signal"]     = df["MACD"] > df["MACD_signal"]
    f["MACD_below_signal"]     = df["MACD"] < df["MACD_signal"]
    f["MACD_cross_up"]         = (df["MACD"] > df["MACD_signal"]) & (df["MACD"].shift(1) <= df["MACD_signal"].shift(1))
    f["MACD_cross_down"]       = (df["MACD"] < df["MACD_signal"]) & (df["MACD"].shift(1) >= df["MACD_signal"].shift(1))
    f["MACD_hist_increasing"]  = df["MACD_hist"] > df["MACD_hist"].shift(1)
    f["MACD_hist_decreasing"]  = df["MACD_hist"] < df["MACD_hist"].shift(1)

    # ── Bulk insert: one shot, no fragmentation ─────────────────────────────
    flags_df = pd.DataFrame(f, index=df.index, copy=False)   # ← build once
    df = pd.concat([df, flags_df], axis=1, copy=False)       # ← bulk join (no warn)
    return df



# ----------------------------------------------------------------------
#  FETCHER  (unchanged except for SMA_5/200 loop already installed)
# ----------------------------------------------------------------------
def fetch_market_data_with_indicators(
    symbol: str,
    intervals=None,
    lookback_periods=None,
    end=None,
    testnet: bool = False,
):
    """
    Fetch OHLCV data for multiple intervals from Bybit, compute indicators,
    alias them for flagging, and append boolean flags.
    Returns a dict {interval: DataFrame}.
    """
    session = HTTP(testnet=testnet)
    symbol  = symbol.upper()

    if intervals is None:
        intervals = ["4h", "2h", "1h", "5m", "15m", "1d"]

    interval_map = {
        '1m': '1',   '5m': '5',   '15m': '15',
        '1h': '60',  '2h': '120', '4h': '240', '1d': 'D',
    }

    # --- end timestamp (ms) -------------------------------------------------------
    if end:
        end_ms = int(end.replace(tzinfo=timezone.utc).timestamp() * 1000) \
                 if isinstance(end, datetime) else int(end)
    else:
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_str = str(end_ms)

    results = {}

    for iv in intervals:
        code = interval_map.get(iv)
        if code is None:
            logging.error(f"Unsupported interval: {iv}")
            results[iv] = None
            continue

        # --- optional look-back ---------------------------------------------------
        start_str = None
        if lookback_periods and iv in lookback_periods:
            start_ms = process_timestamp(lookback_periods[iv])
            if start_ms:
                start_str = str(int(start_ms))

        try:
            resp = session.get_kline(
                category='inverse'
                if symbol.endswith('USD') and not symbol.endswith(('USDT', 'USDC'))
                else 'linear',
                symbol=symbol,
                interval=code,
                limit=200,
                end=end_str,
                start=start_str,
            )

            if resp.get("retCode", 0) != 0:
                logging.warning(f"API error for {symbol}@{iv}: {resp.get('retMsg')}")
                results[iv] = None
                continue

            klines = resp.get('result', {}).get('list', [])
            if not klines:
                logging.warning(f"No kline data for {symbol}@{iv}.")
                results[iv] = None
                continue

            # ------------------------------------------------------------------ #
            # Build tidy DataFrame                                               #
            # ------------------------------------------------------------------ #
            df = pd.DataFrame(
                klines,
                columns=[
                    'startTime', 'open', 'high', 'low',
                    'close', 'volume', 'turnover'
                ],
            )
            df['startTime'] = pd.to_datetime(
                df['startTime'].astype('int64'), unit='ms', utc=True
            )
            df.sort_values('startTime', inplace=True)

            df[['open', 'high', 'low', 'close', 'volume']] = (
                df[['open', 'high', 'low', 'close', 'volume']]
                .apply(pd.to_numeric, errors='coerce')
                .astype(float)
            )
            df = df[['startTime', 'open', 'high', 'low', 'close', 'volume']]

            # ------------------------------------------------------------------ #
            # === core indicator calculations ================================== #
            # ------------------------------------------------------------------ #
            # Volume SMAs
            df['Volume_SMA_5']  = df['volume'].rolling(5).mean()
            df['Volume_SMA_20'] = df['volume'].rolling(20).mean()

            # SMAs (5, 20, 50, 200)
            for w in (5, 20, 50, 200):
                df[f'SMA_{w}'] = ta.trend.SMAIndicator(df['close'], window=w).sma_indicator()

            # RSIs
            df['RSI_14'] = ta.momentum.RSIIndicator(df['close'], 14).rsi()
            df['RSI_9']  = ta.momentum.RSIIndicator(df['close'], 9).rsi()
            df['RSI_21'] = ta.momentum.RSIIndicator(df['close'], 21).rsi()
            df = compute_rsi_low_high(
                df, 21, 'close', 'high', 'low',
                'RSI_21_LOW', 'RSI_21_HIGH'
            )

            # ATR
            df['ATR_14'] = ta.volatility.AverageTrueRange(
                df['high'], df['low'], df['close'], 14
            ).average_true_range()

            # MACD
            macd = ta.trend.MACD(df['close'])
            df['MACD_Line']      = macd.macd()
            df['Signal_Line']    = macd.macd_signal()
            df['MACD_Histogram'] = macd.macd_diff()
            df['MACD_Histogram_Abs']       = df['MACD_Histogram'].abs()
            df['MACD_Histogram_Abs_Avg_20'] = df['MACD_Histogram_Abs'].rolling(20).mean()
            df['MACD_Histogram_Mean_20']    = df['MACD_Histogram'].rolling(20).mean()

            # Bollinger Bands
            bb = ta.volatility.BollingerBands(df['close'])
            df['Bollinger_Upper']  = bb.bollinger_hband()
            df['Bollinger_Middle'] = bb.bollinger_mavg()
            df['Bollinger_Lower']  = bb.bollinger_lband()

            # EMAs
            for w in (9, 14, 20, 21, 50, 200):
                df[f'EMA_{w}'] = ta.trend.EMAIndicator(df['close'], window=w).ema_indicator()

            # Keltner Channels
            df = calculate_keltner_channels(df)

            # VWAP
            df['VWAP'] = ta.volume.VolumeWeightedAveragePrice(
                df['high'], df['low'], df['close'], df['volume']
            ).volume_weighted_average_price()

            # Other momentum / volatility
            df['CCI_14']     = ta.trend.CCIIndicator(df['high'], df['low'], df['close']).cci()
            df['Momentum']   = ta.momentum.ROCIndicator(df['close'], 14).roc()
            df['RSI_Trend']  = df['RSI_14'].diff()
            df['Price_Volatility'] = (df['high'] - df['low']) / df['close']

            # Support, extras, fibs
            df = calculate_support_resistance(df)
            df = calculate_additional_indicators(df)
            df = create_volume_increased_buy(df)
            df = calculate_fibonacci_retracement(df)

            # ------------------------------------------------------------------ #
            # === alias block (everything a later routine expects) ============= #
            # ------------------------------------------------------------------ #
            df.replace([np.inf, -np.inf], np.nan, inplace=True)
            df.fillna(0, inplace=True)

            # Bollinger & Keltner midpoints
            df['BB_upper']         = df['Bollinger_Upper']
            df['BB_middle']        = df['Bollinger_Middle']
            df['BB_lower']         = df['Bollinger_Lower']
            df['BB_upper_middle']  = (df['BB_upper'] + df['BB_middle']) / 2
            df['BB_lower_middle']  = (df['BB_middle'] + df['BB_lower']) / 2

            df['KC_upper']         = df['KC_Upper']
            df['KC_middle']        = df['KC_Middle']
            df['KC_lower']         = df['KC_Lower']
            df['KC_upper_middle']  = (df['KC_upper'] + df['KC_middle']) / 2
            df['KC_lower_middle']  = (df['KC_middle'] + df['KC_lower']) / 2

            # Simple aliases
            df['VOL_SMA_5']  = df['Volume_SMA_5']
            df['VOL_SMA_20'] = df['Volume_SMA_20']
            df['VO']         = df.get('Volume_Oscillator', 0)
            df['ROC_14']     = df['Momentum']
            df['Support_20'] = df['Support']
            df['Resistance_20'] = df['Resistance']
            df['STOCH_K']    = df['Stochastic_%K']
            df['STOCH_D']    = df['Stochastic_%D']
            df['WILLR_14']   = df['Williams_%R']
            df['ADX_14']     = df['ADX']
            df['PLUS_DI_14'] = df['DI+']
            df['MINUS_DI_14'] = df['DI-']
            df['MACD']       = df['MACD_Line']
            df['MACD_signal'] = df['Signal_Line']
            df['MACD_hist']   = df['MACD_Histogram']

            # ------------------------------------------------------------------ #
            # Boolean flags (call the robust flag builder)                        #
            # ------------------------------------------------------------------ #
            df = add_indicator_flags(df, iv, False)

            results[iv] = df

        except Exception as e:
            logging.error(f"Error fetching {symbol}@{iv}: {e}", exc_info=True)
            results[iv] = None

    return results


# --------------------------------------------------------------------
#  SAFE FEATURE NAME ACCESS (cross CatBoost versions)
# --------------------------------------------------------------------
def cat_feature_names(model: CatBoostClassifier) -> List[str]:
    """
    Return the feature names in *training order* for any CatBoost model.
    """
    if hasattr(model, "get_feature_names"):
        return list(model.get_feature_names())
    return list(model.feature_names_)

# --------------------------------------------------------------------
#  SAFE NUMERIC COERCION
# --------------------------------------------------------------------
def _to_float_or_nan(x) -> float:
    """
    Best-effort convert to float; return np.nan on failure.
    """
    try:
        return float(x)
    except Exception:
        return np.nan


# --------------------------------------------------------------------
#  FLATTEN LATEST ROW FROM MULTI-INTERVAL DATA
# --------------------------------------------------------------------
def flatten_indicators_for_model(
    dfs_by_interval: Dict[str, pd.DataFrame],
    expected_cols: Optional[List[str]] = None,
    *,
    drop_time: bool = True,
    prefix_tf: bool = True,
) -> pd.DataFrame:
    """
    Take dict of {timeframe: DataFrame} and produce a *single-row* DataFrame
    of the most recent indicators from each timeframe.

    Column naming convention:
        <col>_<tf>  (e.g., 'RSI_14_4h')

    Parameters
    ----------
    dfs_by_interval : dict[str, DataFrame]
    expected_cols   : optional list of model feature names. If provided,
                      we'll reindex to that list (leave NaNs; *no* 0 fill).
    drop_time       : skip 'startTime' column when flattening.
    prefix_tf       : True → suffix w/ timeframe; False → use raw col names.

    Returns
    -------
    DataFrame shape (1, n_features_raw_before_reindex).
    """
    flat: Dict[str, float] = {}

    for tf, df in dfs_by_interval.items():
        if df is None or df.empty:
            raise ValueError(f"No data for time-frame '{tf}'")

        last = df.iloc[-1]

        for col, val in last.items():
            if drop_time and col == "startTime":
                continue
            name = f"{col}_{tf}" if prefix_tf else col
            flat[name] = _to_float_or_nan(val)

    row = pd.Series(flat, name=0)

    if expected_cols is not None:
        # leave NaNs so we SEE missing features
        row = row.reindex(expected_cols)

    return row.to_frame().T


def load_chronos_cat_run(run_dir: str) -> dict:
    """
    STRICT load for one CatBoost model + metadata from a Chronos export directory.

    Required files:
      • catboost_model_*.cbm
      • metrics_*.json
      • cluster_specs.json
      • feature_importances_*.csv

    Raises FileNotFoundError if any are missing.
    """
    p = Path(run_dir)

    # Model (required)
    cb_paths = list(p.glob("catboost_model_*.cbm"))
    if not cb_paths:
        raise FileNotFoundError(f"[{run_dir}] missing catboost_model_*.cbm")
    cb_path = cb_paths[0]
    model = CatBoostClassifier()
    model.load_model(cb_path)

    # Metrics (required)
    metrics_paths = list(p.glob("metrics_*.json"))
    if not metrics_paths:
        raise FileNotFoundError(f"[{run_dir}] missing metrics_*.json")
    metrics_path = metrics_paths[0]
    metrics = json.loads(metrics_path.read_text())
    thr = float(metrics.get("threshold", 0.5))

    # Cluster specs (required)
    specs_path = p / "cluster_specs.json"
    if not specs_path.exists():
        raise FileNotFoundError(f"[{run_dir}] missing cluster_specs.json")
    with specs_path.open() as fh:
        cluster_specs = json.load(fh)

    # Feature importances (required)
    fi_paths = list(p.glob("feature_importances_*.csv"))
    if not fi_paths:
        raise FileNotFoundError(f"[{run_dir}] missing feature_importances_*.csv")
    fi_path = fi_paths[0]
    importance = pd.read_csv(fi_path)

    return {
        "model":          model,
        "threshold":      thr,
        "cluster_specs":  cluster_specs,
        "importance":     importance,
        "metrics":        metrics,
        "run_dir":        str(p),
    }
def validate_importance_matches_model(run: dict, run_name: str = ""):
    model_feats = cat_feature_names(run["model"])
    fi = run["importance"]
    fi_feats = fi["Feature"].astype(str).tolist()

    missing_in_model = [f for f in fi_feats if f not in model_feats]
    if missing_in_model:
        logging.error("[%s] %d features in FI CSV not found in model: %s%s",
                      run_name, len(missing_in_model),
                      missing_in_model[:20], " …" if len(missing_in_model) > 20 else "")

    missing_in_csv = [f for f in model_feats if f not in fi_feats]
    if missing_in_csv:
        logging.error("[%s] %d model features missing from FI CSV: %s%s",
                      run_name, len(missing_in_csv),
                      missing_in_csv[:20], " …" if len(missing_in_csv) > 20 else "")
# ────────────────────────────────────────────────────────────────
#  LOAD THE TWO RUNS
# ────────────────────────────────────────────────────────────────
# --- Chronos CatBoost runs (MANDATORY FILES) --------------------
LONG_DIR  = "/media/przem/w/Trade/MT1-Chronos/long"
SHORT_DIR = "/media/przem/w/Trade/MT1-Chronos/short"

long_run  = load_chronos_cat_run(LONG_DIR)   # strict loader you defined
short_run = load_chronos_cat_run(SHORT_DIR)

# convenience aliases if you still want bare models around
long_model  = long_run["model"]
short_model = short_run["model"]


validate_importance_matches_model(long_run,  "LONG")
validate_importance_matches_model(short_run, "SHORT")


print("Long-model AUC :",  long_run["metrics"].get("auc"))
print("Short-model AUC:",  short_run["metrics"].get("auc"))

# --------------------------------------------------------------------
#  CLUSTER-SMOOTHING (SIGMOID NORMALIZATION) — OPTIONAL
# --------------------------------------------------------------------
def apply_cluster_smoothing(row_s: pd.Series, cluster_specs: dict) -> pd.Series:
    """
    Append sigmoid-smoothed columns (as during training).

        new_col = 1 / (1 + exp(-(x - μ) / σ))

    cluster_specs must be:
        {
          "<cluster_name>": {
            "<raw_feature_name>": {"mean": μ, "sigma": σ},
            ...
          },
          ...
        }

    NOTE: We *do not* fill missing raw values here; we use 0.0 fallback
    ONLY if the raw feature is absent. Adjust if training used NaNs.
    """
    if not cluster_specs:
        return row_s

    for cluster, feats in cluster_specs.items():
        for feat_name, pars in feats.items():
            col_raw = feat_name                         # e.g. "CCI_14_1h"
            col_new = f"{cluster}_{feat_name}_smooth"
            mu = pars.get("mean", 0.0)
            sigma = max(pars.get("sigma", 1.0), 1e-6)
            x = row_s.get(col_raw, 0.0)
            row_s[col_new] = 1.0 / (1.0 + np.exp(-(x - mu) / sigma))
    return row_s


# --------------------------------------------------------------------
#  FULL-ROW AUDIT LOGGER
# --------------------------------------------------------------------
def audit_model_row(
    row: pd.DataFrame,
    expected_cols: List[str],
    *,
    tag: str = "",
    dump_all: bool = False,
    preview: int = 25,
    logger: logging.Logger = logging.getLogger(),
) -> None:
    """
    Log missing vs extra features before scoring.
    """
    row_cols = row.columns.tolist()

    missing = [c for c in expected_cols if c not in row_cols]
    extra   = [c for c in row_cols       if c not in expected_cols]

    if missing:
        logger.warning(
            f"[ML-AUDIT:{tag}] {len(missing)} features MISSING "
            f"→ {missing[:20]}{' …' if len(missing) > 20 else ''}"
        )
    else:
        logger.info(f"[ML-AUDIT:{tag}] ✅ all {len(expected_cols)} expected features present")

    if extra:
        logger.info(
            f"[ML-AUDIT:{tag}] {len(extra)} EXTRA features (unused by model) "
            f"→ {extra[:20]}{' …' if len(extra) > 20 else ''}"
        )

    if dump_all or preview > 0:
        to_print = row.iloc[0] if dump_all else row.iloc[0, :preview]
        logger.debug(f"[ML-ROW:{tag}] {to_print.to_dict()}")

     
# --------------------------------------------------------------------
#  BUILD 1xN SCORING ROW ALIGNED TO MODEL TRAINING SCHEMA
# --------------------------------------------------------------------
def build_X_for_model(
    dfs_all: Dict[str, pd.DataFrame],
    model: CatBoostClassifier,
    *,
    cluster_specs: Optional[dict] = None,
    run_name: str = "",
    fill_missing: str | float = "nan",
) -> pd.DataFrame:
    """
    Construct the *exact* single-row DataFrame the CatBoost model expects.

    cluster_specs: pass the dict from your run if your model was trained
                   with smoothed features **present in the training schema**.
    fill_missing : "nan" to leave NaNs; numeric to fill missing.
    """
    expected_cols = cat_feature_names(model)

    # 1) Flatten raw indicators (no smoothing yet)
    row_df = flatten_indicators_for_model(dfs_all, expected_cols=None)  # full universe
    audit_model_row(row_df, expected_cols, tag=f"{run_name}:raw")

    row_s = row_df.iloc[0]

    # 2) Optional cluster smoothing BEFORE final reindex (so new cols survive)
    if cluster_specs:
        row_s = apply_cluster_smoothing(row_s, cluster_specs)

    # 3) Final align to training order
    if fill_missing == "nan":
        row_s = row_s.reindex(expected_cols)
    else:
        row_s = row_s.reindex(expected_cols, fill_value=float(fill_missing))

    X = row_s.to_frame().T

    # 4) dtype coercion (numeric)
    X = X.apply(pd.to_numeric, errors="coerce")

    # 5) Audit again after align
    miss_ct = int(X.isna().sum().sum())
    logging.debug("[build_X:%s] aligned row shape=%s NaNs=%d", run_name, X.shape, miss_ct)

    return X
# --------------------------------------------------------------------
#  OPTIONAL: CROSS-CHECK AGAINST feature_importances_*.csv
# --------------------------------------------------------------------
def check_feature_importances_csv(run_dir: str, expected_cols: List[str], *, run_name: str = "") -> None:
    """
    Compare model's feature list vs the feature_importances CSV (if present).
    """
    p = Path(run_dir)
    fi_path = next(p.glob("feature_importances_*.csv"), None)
    if not fi_path:
        logging.warning("[FI:%s] No feature_importances CSV found.", run_name)
        return

    fi = pd.read_csv(fi_path)
    if "Feature" not in fi.columns:
        logging.warning("[FI:%s] CSV missing 'Feature' column.", run_name)
        return

    fi_feats = fi["Feature"].astype(str).tolist()

    missing_in_csv = [f for f in expected_cols if f not in fi_feats]
    extra_in_csv   = [f for f in fi_feats if f not in expected_cols]

    if missing_in_csv:
        logging.warning("[FI:%s] %d model features NOT in CSV: %s%s",
                        run_name, len(missing_in_csv),
                        missing_in_csv[:20],
                        " …" if len(missing_in_csv) > 20 else "")
    if extra_in_csv:
        logging.info("[FI:%s] %d CSV features not in model: %s%s",
                     run_name, len(extra_in_csv),
                     extra_in_csv[:20],
                     " …" if len(extra_in_csv) > 20 else "")


# --------------------------------------------------------------------
#  NORMALIZE CATBOOST PROBABILITY OUTPUT
# --------------------------------------------------------------------
def _extract_pos_class_prob(prob_raw) -> float:
    """
    Normalize CatBoost outputs into a scalar P(positive class).
    """
    arr = np.asarray(prob_raw)
    if arr.ndim == 0:
        return float(arr)
    if arr.ndim == 1:        # (n_samples,) or (1,)
        return float(arr.ravel()[0])
    if arr.ndim == 2:        # (n_samples, n_classes)
        if arr.shape[1] == 1:
            return float(arr[0, 0])
        return float(arr[0, -1])  # assume last column = positive class
    raise ValueError(f"Unexpected prob_raw shape {arr.shape}")


# --------------------------------------------------------------------
#  MASTER SCORING FUNCTION FOR ONE RUN
# --------------------------------------------------------------------
def prob_from_run(run: dict, dfs_all: Dict[str, pd.DataFrame], *, run_name: str = "") -> float:
    """
    Score ONE CatBoost run; return probability for positive class.
    """
    model         = run["model"]
    cluster_specs = run.get("cluster_specs", {})
    X = build_X_for_model(dfs_all, model, cluster_specs=cluster_specs, run_name=run_name, fill_missing="nan")

    try:
        prob_raw = model.predict(X, prediction_type="Probability")
    except Exception:
        logging.exception("[prob_from_run:%s] CatBoost predict failed; returning 0.", run_name)
        return 0.0

    prob = _extract_pos_class_prob(prob_raw)

    label = run.get("metrics", {}).get("label", run.get("name", run_name or "?"))
    logging.info("P(%s) = %.4f", label, prob)
    return float(prob)

# ──────────────────────────────────────────────────────────────────────────────


def fetch_top_trades_ratio(symbol, period='1h'):
    """
    Fetches the top traders' long-to-short position ratio for a given symbol from Bybit API.

    Args:
        symbol (str): Trading pair (e.g., pair).
        period (str): Time period for the data (e.g., "5m", "15m", "30m", "1h", "4h", "1d"). Default is '1h'.

    Returns:
        float: The latest long/short ratio. Returns None if data is unavailable or an error occurs.
    """
    try:
        # Bybit API endpoint for top traders' long/short ratio
        url = "https://api.bybit.com/v2/public/account-ratio"
        params = {
            "symbol": symbol,
            "period": period
        }

        # Make the API request
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Parse the response
        data = response.json()
        if data.get("ret_code") == 0 and "result" in data:
            result = data["result"]
            if isinstance(result, list) and len(result) > 0:
                latest_entry = result[-1]  # Get the most recent data point
                long_short_ratio = float(latest_entry.get("long_short_ratio", 0))
                return long_short_ratio
            else:
                print(f"No data available for symbol: {symbol}")
                return None
        else:
            print(f"Error in API response: {data.get('ret_msg', 'Unknown error')}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"HTTP request error: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        print(f"Error processing data: {e}")
        return None

def detect_ema_crossovers(data):
    """
    Detects bullish and bearish EMA crossovers for EMA 9/21 and EMA 20/50.

    Args:
        data (pd.DataFrame): DataFrame containing market data with EMA columns.

    Returns:
        pd.DataFrame: DataFrame with new columns:
                      - "Bullish_Crossover_9_21": True if EMA 9 crosses above EMA 21.
                      - "Bearish_Crossover_9_21": True if EMA 9 crosses below EMA 21.
                      - "Bullish_Crossover_20_50": True if EMA 20 crosses above EMA 50.
                      - "Bearish_Crossover_20_50": True if EMA 20 crosses below EMA 50.
    """
    try:
        # Ensure the required EMA columns exist
        required_columns = ["EMA_9", "EMA_21", "EMA_20", "EMA_50"]
        for col in required_columns:
            if col not in data.columns:
                raise ValueError(f"Missing required column: {col}")

        # Detect EMA 9/21 crossovers
        data["Bullish_Crossover_9_21"] = (data["EMA_9"] > data["EMA_21"]) & (data["EMA_9"].shift(1) <= data["EMA_21"].shift(1))
        data["Bearish_Crossover_9_21"] = (data["EMA_9"] < data["EMA_21"]) & (data["EMA_9"].shift(1) >= data["EMA_21"].shift(1))

        # Detect EMA 20/50 crossovers
        data["Bullish_Crossover_20_50"] = (data["EMA_20"] > data["EMA_50"]) & (data["EMA_20"].shift(1) <= data["EMA_50"].shift(1))
        data["Bearish_Crossover_20_50"] = (data["EMA_20"] < data["EMA_50"]) & (data["EMA_20"].shift(1) >= data["EMA_50"].shift(1))

        return data

    except Exception as e:
        print(f"Error detecting EMA crossovers: {e}")
        return data

def check_recent_ema_crossovers(market_data_1h):
    """
    Checks if there were bullish or bearish EMA crossovers in the past 5 candles for market_data_1h.

    Args:
        market_data_1h (pd.DataFrame): DataFrame containing 1-hour market data with EMA columns.

    Returns:
        dict: A dictionary indicating whether bullish or bearish crossovers occurred.
    """
    # Ensure the required EMA columns exist
    required_columns = ["EMA_9", "EMA_21", "EMA_20", "EMA_50"]
    for col in required_columns:
        if col not in market_data_1h.columns:
            raise ValueError(f"Missing required column: {col}")

    # Detect EMA crossovers
    market_data_1h = detect_ema_crossovers(market_data_1h)

    # Check the last 5 candles for crossovers
    recent_data = market_data_1h.tail(5)
    bullish_9_21 = recent_data["Bullish_Crossover_9_21"].any()
    bearish_9_21 = recent_data["Bearish_Crossover_9_21"].any()
    bullish_20_50 = recent_data["Bullish_Crossover_20_50"].any()
    bearish_20_50 = recent_data["Bearish_Crossover_20_50"].any()

    return {
        "Bullish_Crossover_9_21": bullish_9_21,
        "Bearish_Crossover_9_21": bearish_9_21,
        "Bullish_Crossover_20_50": bullish_20_50,
        "Bearish_Crossover_20_50": bearish_20_50,
    }
# Function to calculate Kelly Criterion-based leverage
def calculate_kelly_criterion(win_prob, loss_prob, win_ratio, loss_ratio):
    try:
        kelly_fraction = (win_prob * win_ratio - loss_prob * loss_ratio) / (win_ratio * loss_ratio)
        kelly_fraction = max(0, min(kelly_fraction, 1))  # Ensure Kelly fraction is in [0, 1]

        # Map the Kelly fraction [0,1] to the leverage range [10,25]
        # If kelly_fraction=0 => leverage=10
        # If kelly_fraction=1 => leverage=25
        min_leverage = 12
        max_leverage = 15
        leverage = int(min_leverage + kelly_fraction * (max_leverage - min_leverage))
        return leverage
    except ZeroDivisionError:
        min_leverage = 12
        return min_leverage  # Default to minimum leverage if division by zero occurs
    
def calculate_max_leverage(
    symbol: str,
    side: str,
    entry_price: float,
    risk_pct: float = 0.10,
    testnet: bool = False
) -> int:
    """
    Calculates the maximum integer leverage such that a stop-loss
    set at 1/3 of the take-profit distance risks about `risk_pct`
    of equity if hit.

    Args:
        symbol (str): Trading pair (e.g., 'ETHUSDT').
        side (str): 'Buy'/'Sell' or 'LONG'/'SHORT'.
        entry_price (float): Entry price for the position.
        risk_pct (float): Max fractional equity risk (default 0.10).
        testnet (bool): If True, uses testnet tick-size lookup.

    Returns:
        int: Maximum leverage (>=1).
    """
    # normalize side values
    side_norm = 'buy' if side.lower() in ('buy', 'long') else 'sell'
    symbol = symbol.upper()

    # --- Fetch market data & indicators ---
    intervals = ['4h', '1h']
    lookbacks = {'4h': '33 days ago UTC', '1h': '8 days ago UTC'}
    md = fetch_market_data_with_indicators(symbol, intervals, lookbacks)
    df_1h, df_4h = md['1h'], md['4h']

    # Extract Bollinger bands and compute 1/5th band distances
    up1, mid1, low1 = (
        df_1h['Bollinger_Upper'].iloc[-1],
        df_1h['SMA_20'].iloc[-1],
        df_1h['Bollinger_Lower'].iloc[-1]
    )
    up4, mid4, low4 = (
        df_4h['Bollinger_Upper'].iloc[-1],
        df_4h['SMA_20'].iloc[-1],
        df_4h['Bollinger_Lower'].iloc[-1]
    )
    delta1 = (up1 - mid1) / 5 if side_norm == 'buy' else (mid1 - low1) / 5
    delta4 = (up4 - mid4) / 5 if side_norm == 'buy' else (mid4 - low4) / 5

    # --- Compute take-profit ---
    if side_norm == 'buy':
        tp1 = up1 - delta1
        tp4 = up4 - delta4
        take_profit = max(tp1, tp4)
    else:
        tp1 = low1 + delta1
        tp4 = low4 + delta4
        take_profit = min(tp1, tp4)

    # --- Compute stop-loss at 1/3 of profit target ---
    profit_dist = abs(take_profit - entry_price)
    stop_dist = profit_dist / 3

    # --- Leverage so SL hit risks ~risk_pct of equity ---
    loss_pct = (stop_dist / entry_price) if entry_price > 0 else 0
    if loss_pct <= 0:
        return 1
    raw_lev = risk_pct / loss_pct
    leverage = max(1, math.floor(raw_lev))

    # --- (Optional) round TP/SL to tick size (doesn't affect leverage) ---
    tick = get_tick_size(symbol, testnet=testnet)
    if tick:
        prec = int(abs(np.log10(tick)))
        take_profit = round(take_profit, prec)
        # similarly round stop_loss if needed:
        # stop_loss = round(entry_price - stop_dist, prec) if side_norm == 'buy' else round(entry_price + stop_dist, prec)

    return leverage



# ============================
# Model functions
# ============================

def prepare_features(data, lags=6):
    """
    Prepares features and labels for model training or prediction.
    This function ensures feature consistency with the trained model.
    """
    try:
        # Define base features
        base_features = [
            "RSI_14", "MACD_Line", "ATR_14", "SMA_50",
            "Bollinger_Upper", "Bollinger_Lower", "Price_Volatility", "Momentum", "KC_Middle"
        ]

        # Initialize a dictionary to store lagged features
        lagged_features = {}

        # Generate lagged features
        for feature in base_features:
            for lag in range(1, lags + 1):
                lagged_col = f"{feature}_lag{lag}"
                data[lagged_col] = data[feature].shift(lag)
                lagged_features[lagged_col] = data[lagged_col]

        # Combine features
        all_features = base_features + list(lagged_features.keys())

        # Drop rows with NaN values due to lagging
        data.dropna(inplace=True)

        # Prepare feature set (X) and target variable (y)
        X = data[all_features]
        y = np.where(data["close"].shift(-1) > data["close"], 1, 0)  # 1 for up, 0 for down

        return X, y
    except Exception as e:
        print(f"Error preparing features: {e}")
        return pd.DataFrame(), pd.Series()



# ============================
# Strategy important functions
# ============================

# Fetch market data with indicators
lookback_periods = {
    "4h": "33 days ago UTC",  # 200 candles × 4 hours = ~33.33 days
    "2h": "16 days ago UTC",  # 200 candles × 2 hours = ~16.67 days
    "1h": "8 days ago UTC",   # 200 candles × 1 hour = ~8.33 days
    "15m": "2 days ago UTC",  # 200 candles × 15 minutes = ~2.08 days
    "5m": "16 hours ago UTC", # 200 candles × 5 minutes = ~16.67 hours
    "1d": "100 days ago",

}

market_data = fetch_market_data_with_indicators(
    symbol=pair,
    intervals = [
    "4h",  # 4-hour interval
    "2h",  # 2-hour interval
    "1h",  # 1-hour interval
    "5m",  # 5-minute interval
    "15m", # 15-minute interval
    "1d"   # 1-day interval
],
    lookback_periods=lookback_periods
)
# Access data for each interval
data_1h  = market_data["1h"]
data_4h  = market_data["4h"]
data_15m = market_data["15m"]
data_1d = market_data["1d"]

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize the global variable
previous_regime = "Undefined"

def classify_market_regime(data,
                           atr_period=14,
                           atr_ma_period=20,
                           mean_reversion_band=0.05,
                           atr_percentile_threshold=80):
    """
    Classifies the current market regime using technical indicators and predefined rules.
    
    Args:
        data (pd.DataFrame): Market data with indicators.
        atr_period (int): Period for ATR calculation.
        atr_ma_period (int): Period for ATR moving average.
        mean_reversion_band (float): Threshold for mean reversion.
        atr_percentile_threshold (int): Percentile threshold for high volatility classification.
    
    Returns:
        dict: A dictionary with the current regime, whether a regime change occurred,
              and a prediction of potential breakout direction ('bullish', 'bearish', or None).
    """
    global previous_regime

    required_columns = [
        "RSI_14", "MACD_Line", "SMA_50", "ATR_14",
        "Bollinger_Upper", "Bollinger_Lower", "KC_Upper", "KC_Lower", "close", "high", "low",
        "Support", "Resistance", "OBV",
        "Stochastic_%K", "Stochastic_%D", "Williams_%R", "ADX", "DI+", "DI-"
    ]
    
    missing_columns = [col for col in required_columns if col not in data.columns]
    if missing_columns:
        logging.error(f"Missing columns for regime classification: {missing_columns}")
        return {"regime": "Undefined", "regime_change": False, "potential_breakout": None}

    try:
        data["ATR_MA"] = data["ATR_14"].rolling(window=atr_ma_period, min_periods=1).mean()
        latest_atr_ma = data["ATR_MA"].iloc[-1]
        if pd.isna(latest_atr_ma):
            logging.error("Insufficient data for ATR moving average calculation.")
            return {"regime": "Undefined", "regime_change": False, "potential_breakout": None}

        latest = data.iloc[-1]
        close, rsi, macd, sma_50 = latest["close"], latest["RSI_14"], latest["MACD_Line"], latest["SMA_50"]
        atr, bollinger_upper, bollinger_lower = latest["ATR_14"], latest["Bollinger_Upper"], latest["Bollinger_Lower"]
        kc_upper, kc_lower, support, resistance = latest["KC_Upper"], latest["KC_Lower"], latest["Support"], latest["Resistance"]
        obv, stochastic_d, stochastic_k, williams_r = latest["OBV"], latest["Stochastic_%D"], latest["Stochastic_%K"], latest["Williams_%R"]
        adx, di_plus, di_minus = latest.get("ADX"), latest.get("DI+"), latest.get("DI-")

        # ATR Percentile Calculation
        atr_percentile = data["ATR_14"].rank(pct=True).iloc[-1] * 100
        data["BBW"] = (data["Bollinger_Upper"] - data["Bollinger_Lower"]) / data["Bollinger_Upper"]
        bb_width = data["BBW"].iloc[-1]
        
        if atr_percentile > atr_percentile_threshold and bb_width > 0.02:
            volatility_regime = "High Volatility"
        else:
            volatility_regime = "Low Volatility"
        
        if adx > 40 and di_plus > di_minus and rsi > 50 and macd > 0:
            trend_type = "Strong Bullish Trending"
        elif adx > 40 and di_minus > di_plus and rsi < 50 and macd < 0:
            trend_type = "Strong Bearish Trending"
        elif 25 < adx <= 40 and di_plus > di_minus and rsi > 50 and macd > 0:
            trend_type = "Bullish Trending"
        elif 25 < adx <= 40 and di_minus > di_plus and rsi < 50 and macd < 0:
            trend_type = "Bearish Trending"
        elif adx <= 25 and abs(macd) < 10 and 40 <= rsi <= 60 and bollinger_upper > close > bollinger_lower:
            trend_type = "Sideways"
        elif adx <= 25 and 40 <= rsi <= 60 and (bollinger_upper < kc_upper and bollinger_lower > kc_lower and (stochastic_k < 40 or stochastic_k > 60)):
            trend_type = "Mean-Reverting"
        else:
            trend_type = "Undefined"

        initial_regime = f"{trend_type} {volatility_regime}"
        valid_regimes = [
            "Strong Bullish Trending Low Volatility", "Strong Bullish Trending High Volatility",
            "Strong Bearish Trending Low Volatility", "Strong Bearish Trending High Volatility",
            "Bullish Trending Low Volatility", "Bullish Trending High Volatility",
            "Bearish Trending Low Volatility", "Bearish Trending High Volatility",
            "Mean-Reverting Low Volatility", "Mean-Reverting High Volatility",
            "Sideways Low Volatility", "Sideways High Volatility"
        ]
        validated_regime = initial_regime if initial_regime in valid_regimes else "Undefined"
        potential_breakout = "bullish" if close > kc_upper else "bearish" if close < kc_lower else None
        regime_change = validated_regime != previous_regime
        if regime_change:
            logging.info(f"Regime change detected: {previous_regime} -> {validated_regime}")
            previous_regime = validated_regime

        return {
            "regime": validated_regime,
            "regime_change": regime_change,
            "potential_breakout": potential_breakout
        }
    except Exception as e:
        logging.error(f"Error during regime classification: {e}")
        return {"regime": "Undefined", "regime_change": False, "potential_breakout": None}

# Fetch trade history and calculate Kelly-based leverage
trade_stats = fetch_trade_history(pair)
win_prob = trade_stats.get("win_prob", 0.5)
loss_prob = trade_stats.get("loss_prob", 0.5)
win_ratio = trade_stats.get("win_ratio", 1.5)
loss_ratio = trade_stats.get("loss_ratio", 1.0)

kelly_leverage = calculate_kelly_criterion(win_prob, loss_prob, win_ratio, loss_ratio)
DEFAULT_LEVERAGE = kelly_leverage
ATR_MULTIPLIER = 1.5
VOLATILITY_FACTOR = 2
THRESHOLD_LONG = 10
THRESHOLD_SHORT = 10
DEFAULT_RISK_REWARD_RATIO = 1.8  # For demonstration only

DEFAULT_WEIGHTS = {
    "Range_Bound_entry": 15
}

def evaluate_conditions(latest, previous, conditions, weights):
    """
    Evaluate a list of conditions and return a cumulative score.
    conditions: a list of tuples like (condition_bool, weight_key, log_message)
    If condition_bool is True, score += weights[weight_key]
    """
    score = 0
    for cond, w_key, msg in conditions:
        if cond and w_key in weights:
            increment = weights[w_key]
            score += increment
            logging.info(f"{msg} Score increased by {increment:.2f}.")
        elif cond and w_key not in weights:
            logging.warning(f"Weight key {w_key} not found in weights.")
    return score

order_tracker = {}

def place_or_update_sl_tp_orders(
    symbol, position_details, new_stop_loss, new_take_profit, testnet=False
):
    """
    Places or updates stop-loss and take-profit conditional orders using Bybit API.

    Args:
        symbol (str): Trading pair (e.g. 'BTCUSDT').
        position_details (dict): Contains 'quantity' (float) and 'side' ('Buy' or 'Sell').
        new_stop_loss (float): Stop-loss trigger price.
        new_take_profit (float): Take-profit trigger price.
        testnet (bool): If True, uses Bybit testnet.
    """
    # Initialize Bybit client
    # Initialize client
    session = HTTP(
        api_key="5Z37Ko6xX1mPSIctRt",
        api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
        testnet=testnet
    )
    symbol = symbol.upper()
    side = position_details.get("side", "").capitalize()
    quantity = position_details.get("quantity")

    logging.debug(f"SL/TP orders for {symbol}, side={side}, qty={quantity}, SL={new_stop_loss}, TP={new_take_profit}")

    # Determine category
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
    elif symbol.endswith("USDT") or symbol.endswith("USDC"):
        category = "linear"
    else:
        category = "spot"
    logging.debug(f"Category: {category}")

    # 1) Fetch positions
    try:
        resp = session.get_positions(category=category, symbol=symbol)
        logging.debug(f"position response: {resp!r}")
        result = resp.get("result", {})
        # Handle different result shapes
        if isinstance(result, dict) and "list" in result:
            positions = result["list"]
        elif isinstance(result, list):
            positions = result
        else:
            # Single position dict
            positions = [result]
        logging.debug(f"Parsed positions: {positions}")
    except Exception as e:
        logging.error(f"Error fetching positions: {e}")
        logging.debug(traceback.format_exc())
        return

    # 2) Check open position
    if not positions or positions[0].get("size", 0) == 0:
        logging.info("No open position to apply SL/TP")
        return

    # 3) Fetch open orders
    try:
        resp = session.get_open_orders(category=category, symbol=symbol)
        logging.debug(f"open orders response: {resp!r}")
        existing = resp.get("result", {}).get("list", [])
        logging.debug(f"Existing orders: {existing}")
    except Exception as e:
        logging.error(f"Error fetching open orders: {e}")
        logging.debug(traceback.format_exc())
        return

    # 4) Cancel existing
    for o in existing:
        if isinstance(o, dict):
            order_id = o.get("order_id")
            order_type = o.get("order_type")
            logging.info(f"Cancelling order {order_type} #{order_id}")
            try:
                session.cancel_order(category=category, symbol=symbol, order_id=order_id)
            except Exception as e:
                logging.error(f"Error cancelling {order_id}: {e}")
                logging.debug(traceback.format_exc())

    # 5) Get current price
    try:
        tick = session.get_tickers(category=category, symbol=symbol)
        logging.debug(f"Ticker response: {tick!r}")
        current_price = float(tick.get("result", {}).get("list", [])[0].get("lastPrice"))
        logging.debug(f"Current price: {current_price}")
    except Exception as e:
        logging.error(f"Error fetching price: {e}")
        logging.debug(traceback.format_exc())
        return

    # 6) Place SL
    if new_stop_loss is not None:
        sl_side = "Sell" if side == "Buy" else "Buy"
        sl_dir = 2 if new_stop_loss < current_price else 1
        logging.debug(f"Sending SL: side={sl_side}, qty={quantity}, stopLoss={new_stop_loss}, dir={sl_dir}")
        try:
            session.set_trading_stop(
                category=category,
                symbol=symbol,
                side=sl_side,
                orderType="Market",
                qty=quantity,
                stopLoss=new_stop_loss,
                triggerDirection=sl_dir,
                triggerBy="LastPrice",
                timeInForce="GoodTillCancel",
                reduceOnly=True
            )
            logging.info(f"Stop-Loss set at {new_stop_loss}")
        except Exception as e:
            logging.error(f"Error placing SL: {e}")
            logging.debug(traceback.format_exc())

    # 7) Place TP
    if new_take_profit is not None:
        tp_side = "Sell" if side == "Buy" else "Buy"
        tp_dir = 1 if new_take_profit > current_price else 2
        logging.debug(f"Sending TP: side={tp_side}, qty={quantity}, takeProfit={new_take_profit}, dir={tp_dir}")
        try:
            session.set_trading_stop(
                category=category,
                symbol=symbol,
                side=tp_side,
                orderType="Market",
                qty=quantity,
                takeProfit=new_take_profit,
                triggerDirection=tp_dir,
                triggerBy="LastPrice",
                timeInForce="GoodTillCancel",
                reduceOnly=True
            )
            logging.info(f"Take-Profit set at {new_take_profit}")
        except Exception as e:
            logging.error(f"Error placing TP: {e}")
            logging.debug(traceback.format_exc())





def determine_entry_price(
    market_data_1h, market_data_4h,
    market_data_5m, market_data_15m, market_data_1d,
    symbol,
    *,                       # keyword-only from here
    long_model=None,         # default keeps it optional
    short_model=None,
    weights=DEFAULT_WEIGHTS,
    threshold_long=THRESHOLD_LONG,
    threshold_short=THRESHOLD_SHORT,
    default_leverage=DEFAULT_LEVERAGE,
    atr_multiplier=ATR_MULTIPLIER,
    volatility_factor=VOLATILITY_FACTOR,
    previous_regime=None,
    current_regime="Undefined",
    potential_breakout_direction=None
):
    """
    Determines entry prices for LONG and SHORT positions based on the current market regime,
    breakout direction, and various technical indicators.
    
    Args:
        market_data_1h (pd.DataFrame): Market data with indicators for 1-hour interval.
        market_data_4h (pd.DataFrame): Market data with indicators for 4-hour interval.
        market_data_5m (pd.DataFrame): Market data with indicators for 30-minute interval.
        market_data_15m (pd.DataFrame): Market data with indicators for 15-minute interval.
        symbol (str): Trading symbol.
        predicted_direction (str): Predicted market direction ("UP", "DOWN", "NEUTRAL").
        weights (dict): Weights for various indicators.
        threshold_long (float): Threshold score to enter LONG.
        threshold_short (float): Threshold score to enter SHORT.
        default_leverage (int): Default leverage for trades.
        atr_multiplier (float): Multiplier for ATR in stop-loss calculations.
        volatility_factor (float): Factor to adjust volatility calculations.
        previous_regime (str): Previous market regime.
        current_regime (str): Current market regime.
        potential_breakout_direction (str or None): Direction of potential breakout ("bullish", "bearish", or None).
    
    Returns:
        list or None: List of trade signals or None if no signals are generated.
    """
    logging.info(f"Starting determine_entry_price for {symbol}, "
                 f"Current Regime: {current_regime}, Previous Regime: {previous_regime}, "
                 f"Potential Breakout Direction: {potential_breakout_direction}")
    
    required_columns = [
        'RSI_14', 'MACD_Line', 'close', 'volume', 'ADX', 
        'Stochastic_%K', 'CCI', 'Williams_%R',
        'Bollinger_Lower', 'Bollinger_Upper','Bollinger_Middle',
        'KC_Lower', 'KC_Upper',
        'EMA_20','EMA_200','EMA_50', 'ATR_14', 'Support', 'Resistance', 'Regime',
        'high', 'low','Volume_SMA_20',"Volume_SMA_5"  # Added 'high' and 'low' for ATR calculation if needed
    ]

    # Select the appropriate DataFrame based on the regime
    if current_regime in ["bullish_trending", "bearish_trending", "Strong Bullish Trending", "Strong Bearish Trending"]:
        data = market_data_1h
    else:
        data = market_data_4h

    missing_cols = [c for c in required_columns if c not in data.columns]
    if missing_cols:
        logging.error(f"Missing columns: {missing_cols}")
        return None

    if len(data) < 2:
        logging.error("Not enough rows in data to get latest and previous candles.")
        return None

    latest = data.iloc[-1]
    previous = data.iloc[-2]

    # Basic sanity checks for NaNs
    if latest.isnull().any():
        logging.warning("NaNs in latest row. Cannot proceed.")
        return None

    ratio = fetch_top_trades_ratio(symbol) or 1.0  # Implement this function accordingly
    logging.info(f"Long/Short ratio: {ratio}")

    # Copy weights to avoid mutating global defaults
    weights = weights.copy()


    atr = latest.get('ATR_14', 0)
    if atr == 0:
        logging.warning("ATR_14 = 0, check your ATR calculations.")
    adjusted_atr = atr * atr_multiplier
    volatility = atr * volatility_factor
    logging.info(f"Adjusted ATR: {adjusted_atr}, Volatility: {volatility}")

    support = latest.get('Support')
    resistance = latest.get('Resistance')
    if support is None or resistance is None:
        logging.warning("Support/Resistance not found, using fallback.")
        support = previous['close'] - adjusted_atr
        resistance = previous['close'] + adjusted_atr

    regime = latest.get('Regime', current_regime)
    logging.info(f"Regime: {regime}")




    # Adjust weights based on potential breakout direction
    if potential_breakout_direction == "bullish":
        if "potential_breakout_bullish" in weights:
            weights["potential_breakout_bullish"] *= 1.5  # Example multiplier
            logging.info(f"Potential bullish breakout detected. Increased 'potential_breakout_bullish' weight to {weights['potential_breakout_bullish']}.")
        else:
            logging.warning("Weight key 'potential_breakout_bullish' not found in weights.")
    elif potential_breakout_direction == "bearish":
        if "potential_breakout_bearish" in weights:
            weights["potential_breakout_bearish"] *= 1.5  # Example multiplier
            logging.info(f"Potential bearish breakout detected. Increased 'potential_breakout_bearish' weight to {weights['potential_breakout_bearish']}.")
        else:
            logging.warning("Weight key 'potential_breakout_bearish' not found in weights.")

    trade_signals = []


    # Map regime to evaluation functions
    regime_evaluation_functions = {
        'Mean-Reverting Low Volatility': evaluate_generic_conditions,
        'Mean-Reverting Bearish Low Volatility': evaluate_generic_conditions,
        'Mean-Reverting Bullish Low Volatility': evaluate_generic_conditions,
        'Sideways Low Volatility': evaluate_generic_conditions,
        'Bullish Trending Low Volatility': evaluate_generic_conditions,
        'Bearish Trending Low Volatility': evaluate_generic_conditions,
        'Mean-Reverting High Volatility': evaluate_generic_conditions,
        'Mean-Reverting Bearish High Volatility': evaluate_generic_conditions,
        'Mean-Reverting Bullish High Volatility': evaluate_generic_conditions,
        'Sideways High Volatility': evaluate_generic_conditions,
        'Bullish Trending High Volatility': evaluate_generic_conditions,
        'Bearish Trending High Volatility': evaluate_generic_conditions,
        'Strong Bullish Trending Low Volatility': evaluate_generic_conditions,
        'Strong Bullish Trending High Volatility': evaluate_generic_conditions,
        'Strong Bearish Trending Low Volatility': evaluate_generic_conditions,
        'Strong Bearish Trending High Volatility': evaluate_generic_conditions
    }

    # Select the appropriate evaluation function based on current regime
    evaluation_func = regime_evaluation_functions.get(regime, evaluate_generic_conditions)

    # Call the evaluation function with the necessary parameters, including breakout direction
    if current_regime in ["bullish_trending", "bearish_trending", "Strong Bullish Trending", "Strong Bearish Trending"]:
        evaluation_func(
            market_data_1h=market_data_1h,
            market_data_4h=market_data_4h,
            latest=latest,
            previous=previous,
            weights=weights,
            THRESHOLD_LONG=threshold_long,
            THRESHOLD_SHORT=threshold_short,
            support=support,
            resistance=resistance,
            buffer=0,
            adjusted_atr=adjusted_atr,
            trade_signals=trade_signals,
            ratio=ratio,
            long_model=long_model,        # ← ADD
            short_model=short_model
    
        )
    else:
        # Ensure market_data_5m and market_data_15m are DataFrames
        if not isinstance(market_data_5m, pd.DataFrame) or not isinstance(market_data_15m, pd.DataFrame):
            logging.error("market_data_5m or market_data_15m is not a DataFrame.")
            return None

        evaluation_func(
            market_data_1d=market_data_1d,
            market_data_5m=market_data_5m,
            market_data_15m=market_data_15m,
            market_data_1h=market_data_1h,
            market_data_4h=market_data_4h,
            latest=latest,
            previous=previous,
            weights=weights,
            THRESHOLD_LONG=threshold_long,
            THRESHOLD_SHORT=threshold_short,
            support=support,
            resistance=resistance,
            buffer=0,
            adjusted_atr=adjusted_atr,
            trade_signals=trade_signals,
            ratio=ratio,
            long_model=long_model,        # ← ADD
            short_model=short_model      # ← ADD
        )

    if not trade_signals:
        # Fallback logic with Keltner Channels
        k_upper = latest['KC_Upper']
        k_lower = latest['KC_Lower']
        close_price = latest['close']

        # Only do fallback if volatility is not too low
        # If volatility is low (ATR too small), skip fallback to avoid poor risk/reward
        if atr > 0.0 and volatility > (atr * 2.0):  # Example: require some minimum volatility
            if close_price > k_upper:
                entry_price = k_upper + 0.15 * atr
                logging.info("Fallback: Entering LONG above Keltner Upper")
                trade_signals.append({
                    'action': 'LONG',
                    'entry_price': entry_price,
                    'stop_loss': entry_price - adjusted_atr,
                    'take_profit': entry_price + adjusted_atr,
                    'leverage': DEFAULT_LEVERAGE,
                    'trailing_stop': True
                })
            elif close_price < k_lower:
                entry_price = k_lower - 0.15 * atr
                logging.info("Fallback: Entering SHORT below Keltner Lower")
                trade_signals.append({
                    'action': 'SHORT',
                    'entry_price': entry_price,
                    'stop_loss': entry_price + adjusted_atr,
                    'take_profit': entry_price - adjusted_atr,
                    'leverage': default_leverage,
                    'trailing_stop': True
                })
            else:
                logging.info("No fallback conditions met. No trade signals.")
        else:
            logging.info("Volatility too low for fallback trades. No trade signals.")
    if trade_signals:
        for i, sig in enumerate(trade_signals, start=1):
            logging.info(f"Trade Signal {i}: {sig}")
            # Assuming position_details is available in the context
            position_details = {
                "quantity": latest.get("quantity", 1),  # Replace with actual quantity logic
                "side": "Buy" if sig['action'] == 'LONG' else "Sell"
            }
            place_or_update_sl_tp_orders(symbol, position_details, sig['stop_loss'], sig['take_profit'])
        return trade_signals
    else:
        logging.warning(f"No signals generated. Holding position for {symbol}.")
        return None
    



# ------------------------------------------------------------------

# ------------------------------------------------------------------

# ──────────────────────── MAIN FUNCTION ─────────────────────────
def evaluate_generic_conditions(
    market_data_5m: pd.DataFrame,
    market_data_15m: pd.DataFrame,
    market_data_1d: pd.DataFrame,
    market_data_1h: pd.DataFrame,
    market_data_4h: pd.DataFrame,
    latest,
    previous,
    weights,
    THRESHOLD_LONG: float,
    THRESHOLD_SHORT: float,
    support,
    resistance,
    buffer,
    adjusted_atr: float,
    trade_signals: list,
    ratio,
    *,
    long_run: dict,              # <-- full Chronos run dict (model + threshold + specs)
    short_run: dict,             # <-- full Chronos run dict
    fill_missing_guard: float = 0.20,  # if >20% features missing, suppress ML gate
    missing_guard_action: str = "suppress",  # "suppress" | "neutral" | "allow"
):
    """
    4h breakout hard filters + ML gating using *two* CatBoost Chronos runs.

    Parameters
    ----------
    market_data_*      : DataFrames for each timeframe (already indicator-enriched).
    THRESHOLD_LONG/SHORT:
        Strategy-level score cutoffs (your external config).
    long_run, short_run:
        Dicts from `load_chronos_cat_run()`.
    fill_missing_guard :
        Fraction (0..1). If actual missing / total features > this,
        we treat ML prob as untrustworthy (see missing_guard_action).
    missing_guard_action :
        "suppress" -> don't add ML score (act as if gate failed).
        "neutral"  -> treat prob = 0.5 (so gate likely fails if threshold >0.5).
        "allow"    -> ignore guard; always respect model prob.

    Returns
    -------
    (score_long, score_short, p_long, p_short)
    """

    # ───────────────────────── constants ─────────────────────────
    FIXED_ML_SCORE = 10.0
    BLOCK_PENALTY  = 999.0

    LONG_GATE  = float(long_run["threshold"])
    SHORT_GATE = float(short_run["threshold"])

    score_long  = 0.0
    score_short = 0.0

    # ────────────────── 4h price-action hard filters ─────────────
    # LONG block if bearish breakout conditions
    bearish_px_breakout = (
        market_data_4h["ADX"].iloc[-1] < 20 and (
            market_data_4h["Bollinger_Lower"].iloc[-1] > market_data_4h["close"].iloc[-1] or
            market_data_4h["Bollinger_Lower"].iloc[-2] > market_data_4h["close"].iloc[-2] or
            market_data_4h["Support"].iloc[-2]         > market_data_4h["close"].iloc[-1] or
            market_data_4h["Support"].iloc[-3]         > market_data_4h["close"].iloc[-2] or
            market_data_4h["KC_Lower"].iloc[-1]        > market_data_4h["close"].iloc[-1] or
            market_data_4h["KC_Lower"].iloc[-2]        > market_data_4h["close"].iloc[-2]
        )
    )
    if bearish_px_breakout:
        score_long -= BLOCK_PENALTY
        logging.info("⚠ 4h bearish price breakout – LONGs blocked")

    # SHORT block if bullish breakout conditions
    bullish_px_breakout = (
        market_data_4h["ADX"].iloc[-1] < 20 and (
            market_data_4h["Bollinger_Upper"].iloc[-1] < market_data_4h["close"].iloc[-1] or
            market_data_4h["Bollinger_Upper"].iloc[-2] < market_data_4h["close"].iloc[-2] or
            market_data_4h["Resistance"].iloc[-2]      < market_data_4h["close"].iloc[-1] or
            market_data_4h["Resistance"].iloc[-3]      < market_data_4h["close"].iloc[-2] or
            market_data_4h["KC_Upper"].iloc[-1]        < market_data_4h["close"].iloc[-1] or
            market_data_4h["KC_Upper"].iloc[-2]        < market_data_4h["close"].iloc[-2]
        )
    )
    if bullish_px_breakout:
        score_short -= BLOCK_PENALTY
        logging.info("⚠ 4h bullish price breakout – SHORTs blocked")

    # ────────────────── assemble multi-timeframe dict ─────────────
    dfs_all = {
        "5m":  market_data_5m,
        "15m": market_data_15m,
        "1h":  market_data_1h,
        "4h":  market_data_4h,
        "1d":  market_data_1d,
    }

    # ────────────────── ML probabilities ──────────────────────────
    p_long = p_short = 0.0
    miss_long = miss_short = 0.0

    try:
        # Build aligned matrices ourselves so we can inspect missing %
        X_long = build_X_for_model(
            dfs_all,
            long_run["model"],
            cluster_specs=long_run.get("cluster_specs", {}),
            run_name="LONG",
            fill_missing="nan",
        )
        X_short = build_X_for_model(
            dfs_all,
            short_run["model"],
            cluster_specs=short_run.get("cluster_specs", {}),
            run_name="SHORT",
            fill_missing="nan",
        )

        # missing fraction
        miss_long  = X_long.isna().mean(axis=1).iloc[0]
        miss_short = X_short.isna().mean(axis=1).iloc[0]

        # Score (note: prob_from_run rebuilds X; we could reuse X_* but prob_from_run is small)
        p_long  = prob_from_run(long_run,  dfs_all, run_name="LONG")
        p_short = prob_from_run(short_run, dfs_all, run_name="SHORT")

    except Exception:
        logging.exception("Model inference failed – forcing ML probs=0.")
        p_long = p_short = 0.0

    logging.info(f"ML probs → long={p_long:.3f} | short={p_short:.3f} "
                 f"(missing_long={miss_long:.2%}, missing_short={miss_short:.2%})")

    # ────────────────── ML gating w/ missing-guard ────────────────
    def _guard(prob, miss_frac, gate, side_name):
        """
        Decide whether ML score can be applied given missing data.
        """
        allow = True
        if miss_frac > fill_missing_guard and missing_guard_action != "allow":
            if missing_guard_action == "suppress":
                allow = False
                logging.warning("[ML-GUARD:%s] %.1f%% features missing > %.1f%% guard; ML score suppressed.",
                                side_name, 100 * miss_frac, 100 * fill_missing_guard)
            elif missing_guard_action == "neutral":
                logging.warning("[ML-GUARD:%s] %.1f%% features missing; substituting prob=0.5.",
                                side_name, 100 * miss_frac)
                prob = 0.5
        if allow and prob >= gate:
            return prob, True
        return prob, False

    p_long, gate_long_pass = _guard(p_long, miss_long, LONG_GATE, "LONG")
    p_short, gate_short_pass = _guard(p_short, miss_short, SHORT_GATE, "SHORT")

    if gate_long_pass:
        score_long += FIXED_ML_SCORE
    if gate_short_pass:
        score_short += FIXED_ML_SCORE

    logging.info(f"Total LONG score  : {score_long:.2f}")
    logging.info(f"Total SHORT score : {score_short:.2f}")

    # ────────────────── LONG entry block ──────────────────────────
    if score_long >= THRESHOLD_LONG:
        boll_low_15  = market_data_15m["Bollinger_Lower"].iloc[-1]
        boll_mid_15  = market_data_15m["Bollinger_Middle"].iloc[-1]
        boll_low_1h  = market_data_1h["Bollinger_Lower"].iloc[-1]
        midpoint_15  = (boll_low_15 + boll_mid_15) / 2
        entry_long   = boll_low_1h if midpoint_15 < boll_low_1h else midpoint_15

        if market_data_15m["close"].iloc[-1] <= entry_long:
            tp_long = market_data_1h["SMA_20"].iloc[-1]
            if tp_long >= entry_long * 1.006:
                trade_signals.append({
                    "action": "LONG",
                    "entry_price": entry_long,
                    "stop_loss":   entry_long - adjusted_atr,
                    "take_profit": tp_long,
                    "leverage":    DEFAULT_LEVERAGE,
                    "trailing_stop": True,
                })
                logging.info("→ LONG signal queued")

    # ────────────────── SHORT entry block ─────────────────────────
    if score_short >= THRESHOLD_SHORT:
        boll_up_5   = market_data_5m["Bollinger_Upper"].iloc[-1]
        boll_mid_5  = market_data_5m["Bollinger_Middle"].iloc[-1]
        boll_up_1h  = market_data_1h["Bollinger_Upper"].iloc[-1]

        midpoint_5  = (boll_up_5 + boll_mid_5) / 2
        entry_short = boll_up_1h if midpoint_5 > boll_up_1h else midpoint_5

        if market_data_5m["close"].iloc[-1] >= entry_short:
            tp_short = market_data_1h["Bollinger_Lower"].iloc[-1]
            if tp_short <= entry_short * 0.994:
                trade_signals.append({
                    "action": "SHORT",
                    "entry_price": entry_short,
                    "stop_loss":   entry_short + adjusted_atr,
                    "take_profit": tp_short,
                    "leverage":    DEFAULT_LEVERAGE,
                    "trailing_stop": True,
                })
                logging.info("→ SHORT signal queued")

    return score_long, score_short, p_long, p_short

# Global variable to track the previous regime
previous_regime = None

def detect_regime_change(current_regime):
    """
    Detects if there is a change in the market regime.

    Args:
        current_regime (str): The current market regime.

    Returns:
        dict: Contains the current regime and whether a regime change has occurred.
    """
    global previous_regime

    # Check if there is a change in regime
    regime_change = current_regime != previous_regime

    if regime_change:
        print(f"Regime change detected: {previous_regime} -> {current_regime}")
        previous_regime = current_regime  # Update the global variable to track the new regime
    else:
        print(f"No regime change. Current regime remains: {current_regime}")

    return {"regime": current_regime, "regime_change": regime_change}

#function to generate trade signal

def hold_signal():
    return {
        "action": "HOLD",
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "leverage": None,
        "trailing_stop": None
    }


def get_available_margin(update_after_order=True, symbol=pair, testnet=False):
    """
    Fetches and optionally updates the available margin (totalMarginBalance) from Bybit wallet balances for a Unified Account.

    Args:
        update_after_order (bool): If False, resets the tracker to current available margin.
        symbol (str): Symbol alias for clarity (not used in calculation).
        testnet (bool): If True, uses Bybit testnet.

    Returns:
        float: The tracked available margin.
    """
    global available_margin_tracker
    # Initialize the session with API keys
    session = HTTP(
        api_key="5Z37Ko6xX1mPSIctRt",
        api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
        testnet=testnet
    )

    try:
        # Fetch wallet balances for the Unified Account and extract totalMarginBalance
        resp = session.get_wallet_balance(accountType="UNIFIED")['result']['list'][0]['totalMarginBalance']
        
        # Convert the response to a float
        available_margin = float(resp)

        # Initialize or update tracker
        if available_margin_tracker is None or not update_after_order:
            available_margin_tracker = available_margin
        else:
            # Keep previous tracker but ensure non-negative
            available_margin_tracker = max(0.0, available_margin_tracker)

        print(f"Available margin (totalMarginBalance): {available_margin_tracker:.2f} USDT")
        return available_margin_tracker

    except Exception as e:
        print(f"Error fetching available margin: {e}")
        return 0.0


def get_combined_balance(testnet=False, retries=3, backoff_factor=2):
    """
    Fetches the USDT wallet balance from Bybit with retry logic.

    Args:
        testnet (bool): If True, use Bybit testnet.
        retries (int): Number of retry attempts on failure.
        backoff_factor (int): Multiplier for backoff between retries.

    Returns:
        float: USDT balance, or 0 on error.
    """
    session = HTTP(
        api_key="5Z37Ko6xX1mPSIctRt",
        api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
        testnet=testnet
    )

    attempt = 0
    while attempt < retries:
        try:
            resp = session.get_wallet_balance(accountType="UNIFIED")

            if resp.get("retCode") != 0:
                print(f"Bybit API error fetching USDT balance: {resp.get('retMsg')}")
                return 0.0

            coins = resp.get("result", {}).get("list", [{}])[0].get("coin", [])
            for coin in coins:
                if coin.get("coin") == "USDT":
                    return float(coin.get("walletBalance", 0))

            print("USDT balance not found in the API response.")
            return 0.0

        except (requests.exceptions.ReadTimeout, FailedRequestError, InvalidRequestError) as e:
            print(f"Attempt {attempt + 1} - Bybit API read timeout or request error: {e}")
        except Exception as e:
            print(f"Attempt {attempt + 1} - Unexpected error: {e}")

        attempt += 1
        sleep_time = backoff_factor ** attempt
        print(f"Retrying in {sleep_time} seconds...")
        time.sleep(sleep_time)

    print("All retries failed. Returning 0.")
    return 0.0

def calculate_trade_quantity(
    wallet_balance,  # placeholder, actual margin fetched from API
    leverage,
    entry_price,
    min_quantity=0.002,
    symbol=pair,
    testnet=False
):
    """
    Calculates trade quantity using Bybit API rules:
      - Fetches available margin and combined balance.
      - Applies leverage.
      - Enforces minimum quantity and exchange filters (lot size, notional).

    Args:
        wallet_balance (float): (unused) placeholder for compatibility.
        leverage (float): Leverage multiplier.
        entry_price (float): Price of entry.
        min_quantity (float): Minimum trade quantity.
        symbol (str): Trading symbol.
        testnet (bool): If True, use Bybit testnet.

    Returns:
        float or None: Quantity sized to rules, or None if not feasible.
    """
    # Initialize API
    session = HTTP(testnet=testnet)
    symbol = symbol.upper()

    # Determine product category
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
    elif symbol.endswith("USDT") or symbol.endswith("USDC"):
        category = "linear"
    else:
        category = "spot"

    # Validate entry price
    if entry_price is None or entry_price <= 0:
        print("Error: invalid entry_price")
        return None

    # Fetch margins
    try:
        available_margin = get_available_margin(testnet=testnet)
        combined_balance = get_combined_balance(testnet=testnet)
    except Exception as e:
        print(f"Error fetching margin/balance: {e}")
        return None

    # Use higher of the two
    if combined_balance > available_margin:
        available_margin = combined_balance

    if available_margin <= 0:
        print("Insufficient margin.")
        return None

    # Compute max position value
    max_notional = available_margin * leverage
    quantity = max_notional / entry_price

    # Fetch symbol info for filters
    try:
        response = session.get_instruments_info(category=category, symbol=symbol)
        
        # Print the entire response for debugging
        
        # Check if the response is valid
        if response['retCode'] != 0:
            print(f"Error fetching symbol info: {response['retMsg']}")
            return None
        
        # Extract the list of instruments
        instruments = response.get("result", {}).get("list", [])
        
        # If the symbol is not found, return None
        symbol_info = next((item for item in instruments if item["symbol"] == symbol), None)
        
        if not symbol_info:
            print(f"No symbol info found for {symbol}.")
            return None
        
        # Extract lot size filter
        lot = symbol_info.get("lotSizeFilter", {})
        min_trd_qty = float(lot.get("minOrderQty", 0))
        qty_step = float(lot.get("qtyStep", 0))

        # Extract notional filter if exists
        notional = symbol_info.get("lotSizeFilter", {})
        min_notional = float(notional.get("minNotionalValue", 0))
        
    except Exception as e:
        print(f"Error fetching symbol info: {e}")
        return None

    # Enforce min notional
    if min_notional and quantity * entry_price < min_notional:
        needed = min_notional / entry_price
        if needed * entry_price > max_notional:
            print("Cannot meet minimum notional requirement.")
            return None
        quantity = needed

    # Round down to qty step
    if qty_step > 0:
        quantity = (quantity // qty_step) * qty_step

    # Enforce min trade qty
    if quantity < max(min_quantity, min_trd_qty):
        print("Quantity below minimum trade size.")
        return None

    print(f"Calculated quantity: {quantity}")
    return quantity


def generate_trade_signal(
    market_data_1h, market_data_4h,
    market_data_5m, market_data_15m, market_data_1d,
    regime, *,                    # ← put the * here
    regime_change=False,          # you may keep this if you like
    symbol=pair,
    long_model=None,              # keyword-only, default None
    short_model=None,

     
):
    """
    Generate trade signals based on market regime, indicators, and predicted market direction.
    Includes logic to skip trades when volatility (ATR) is too low.
    """

    logging.info(f"Generating trade signal for {symbol} under regime '{regime}' with predicted direction'.")

    try:
        # Step 1: Fetch trade stats
        trade_stats = fetch_trade_history(symbol)
        win_prob = trade_stats.get("win_prob", 0.5)
        loss_prob = trade_stats.get("loss_prob", 0.5)
        win_ratio = trade_stats.get("win_ratio", 1.5)
        loss_ratio = trade_stats.get("loss_ratio", 1.0)

        logging.debug(f"Fetched trade stats - Win Prob: {win_prob}, Loss Prob: {loss_prob}, Win Ratio: {win_ratio}, Loss Ratio: {loss_ratio}")

        # Step 2: Ensure required columns
        required_columns = [
            "close", "ATR_14", "Support", "Resistance", "EMA_20",
            "Bollinger_Lower", "Bollinger_Upper", "MACD_Line", "RSI_14",
            "KC_Upper", "KC_Lower", "volume"
        ]
        for col in required_columns:
            if col not in market_data_4h.columns:
                logging.warning(f"{col} missing from 4-hour data. Using default values.")
                if col in ["volume", "Price_Volatility"]:
                    market_data_4h[col] = 1
                    logging.debug(f"Set default value for {col}: 1")
                else:
                    market_data_4h[col] = market_data_4h["close"]
                    logging.debug(f"Set {col} to 'close' price.")
        logging.debug("All required columns are present or defaulted in 4-hour data.")

        for col in required_columns:
            if col not in market_data_1h.columns:
                logging.warning(f"{col} missing from 1-hour data. Using default values.")
                if col in ["volume", "Price_Volatility"]:
                    market_data_1h[col] = 1
                    logging.debug(f"Set default value for {col}: 1")
                else:
                    market_data_1h[col] = market_data_1h["close"]
                    logging.debug(f"Set {col} to 'close' price.")
        logging.debug("All required columns are present or defaulted in 1-hour data.")

        # Volatility Check
        # If ATR is too low, skip trading to avoid unprofitable low-volatility conditions.
        LOW_VOLATILITY_THRESHOLD = 0  # Example threshold, adjust as needed. FOR NOW, SET TO 0 REMEMBER TO TEST IN FUTURE AND EXPERIMENT WITH DIFFRENT VALUES
        current_atr = market_data_4h.iloc[-1]["ATR_14"]  # Use 4-hour data for volatility check
        if current_atr < LOW_VOLATILITY_THRESHOLD:
            logging.info(f"Current ATR ({current_atr:.2f}) below threshold ({LOW_VOLATILITY_THRESHOLD}). Holding position to avoid low volatility trades.")
            return hold_signal()

        # Step 3: Determine entry price
        entry_signals = determine_entry_price(
            market_data_1h=market_data_1h,
            market_data_4h=market_data_4h,
            market_data_5m=market_data_5m,
            market_data_15m=market_data_15m,
            market_data_1d=market_data_1d,
            symbol=symbol,
            long_model=long_model,          # NEW
            short_model=short_model,         # NEW

        )

        if not entry_signals or not isinstance(entry_signals, list):
            logging.warning("No valid entry price determined. Holding position.")
            return hold_signal()

        logging.debug(f"Entry signals received: {entry_signals}")

        # Step 4: Adjust Trade Signals Based on Predicted Direction
        adjusted_trade_signals = []
        for idx, signal in enumerate(entry_signals, start=1):
            signal_action = signal.get("action")
            entry_price = signal.get("entry_price")
            stop_loss = signal.get("stop_loss")
            take_profit = signal.get("take_profit")
            signal_leverage = signal.get("leverage", 10)
            trailing_stop = signal.get("trailing_stop", True)
            # Calculate ATR-based leverage
# ---- New leverage calculation ----
            side           = signal_action   # "Buy" or "Sell"
            entry_price    = signal.get("entry_price")
            # risk_pct default is 0.10 (10%), but you can pass e.g. 0.05 for 5%
            leverage_atr = calculate_max_leverage(symbol, side, entry_price)

            logging.debug(f"Processing Entry Signal {idx}: Action: {signal_action}, Entry Price: {entry_price}, Stop Loss: {stop_loss}, Take Profit: {take_profit}, Leverage: {signal_leverage}, Trailing Stop: {trailing_stop}")

            # Check if market_data_1d is None or empty before proceeding
            if market_data_1d is None or market_data_1d.empty:
                logging.error(f"market_data_1d is None or empty for {symbol}. Skipping trade signal generation.")
                return hold_signal()

            # Log the values of the relevant columns in market_data_1d before making the comparison
            # === Skip Trades on 1D Breakout Conditions ===
            # === Skip Trades on 1D Breakout Conditions ===
            latest_1d = market_data_1d.iloc[-1]
            prev_1d = market_data_1d.iloc[-2]
            prev2_1d = market_data_1d.iloc[-3]

            # Bearish breakout zone
            if (
                latest_1d["ADX"] < 20 and (
                latest_1d["Bollinger_Lower"] > latest_1d["close"] or
                prev_1d["Bollinger_Lower"] > prev_1d["close"]) or
                prev_1d["Support"] > latest_1d["close"] or
                prev2_1d["Support"] > prev_1d["close"] or
                latest_1d["KC_Lower"] > latest_1d["close"] or
                prev_1d["KC_Lower"] > prev_1d["close"]
            ):
                logging.info(f"{symbol}: 1D chart shows potential bearish breakout. Skipping this trade signal.")
                continue

            # Bullish breakout zone
            if (
                latest_1d["ADX"] < 20 and (
                latest_1d["Bollinger_Upper"] < latest_1d["close"] or
                prev_1d["Bollinger_Upper"] < prev_1d["close"]) or
                prev_1d["Resistance"] < latest_1d["high"] or
                prev2_1d["Resistance"] < prev_1d["close"] or
                latest_1d["KC_Upper"] < latest_1d["close"] or
                prev_1d["KC_Upper"] < prev_1d["close"]
            ):
                logging.info(f"{symbol}: 1D chart shows potential bullish breakout. Skipping this trade signal.")
                continue

            adjusted_trade_signals.append({
                "action": "Buy" if signal_action == "LONG" else "Sell",
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "leverage": leverage_atr,
                "trailing_stop": trailing_stop
            })

        logging.debug(f"Adjusted trade signals: {adjusted_trade_signals}")

        if not adjusted_trade_signals:
            logging.warning("No adjusted trade signals. Holding position.")
            return hold_signal()

        # Step 5: Select the trade signal if there is exactly one, otherwise skip the trade
        if len(adjusted_trade_signals) == 1:
            best_signal = adjusted_trade_signals[0]
            action = best_signal["action"]
            entry_price = best_signal["entry_price"]
            stop_loss = best_signal["stop_loss"]
            take_profit = best_signal["take_profit"]
            leverage = leverage_atr
            trailing_stop = best_signal["trailing_stop"]

            logging.info(f"Selected Trade Signal - Action: {action}, Entry Price: {entry_price}, Stop Loss: {stop_loss}, Take Profit: {take_profit}, Leverage: {leverage}, Trailing Stop: {trailing_stop}")

            # Step 6: Build trade signal
            trade_signal = {
                "action": action,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "leverage": leverage_atr,
                "trailing_stop": trailing_stop
            }

            # Step 7: Calculate Trade Quantity using existing calculate_trade_quantity function
            wallet_balance = get_combined_balance()  # Ensure this function is defined
            quantity = calculate_trade_quantity(
                wallet_balance=wallet_balance,
                leverage=leverage_atr,
                entry_price=entry_price,
                min_quantity=0.002,  # Adjust as needed
                symbol=symbol,
                testnet=False
            )

            if quantity is None:
                logging.warning("Trade quantity calculation failed. Holding position.")
                return hold_signal()

            logging.debug(f"Calculated trade quantity: {quantity}")

            # Step 8: Place or Update SL and TP Orders
            position_details = {
                "quantity": quantity,
                "side": "Buy" if action == "Buy" else "Sell"
            }
            place_or_update_sl_tp_orders(
                symbol=symbol,
                position_details=position_details,
                new_stop_loss=stop_loss,
                new_take_profit=take_profit
            )
            logging.info(f"Placed/Updated SL and TP orders for {action} position.")

            return trade_signal
        else:
            logging.info("More than one trade signal found. Skipping trade and waiting for 90 seconds.")
            time.sleep(90)
            return hold_signal()

    except KeyError as e:
        logging.error(f"KeyError in generate_trade_signal: {e}")
        logging.error(f"Available columns: {market_data_4h.columns.tolist()}")
        return hold_signal()
    except Exception as e:
        logging.error(f"Error generating trade signal: {e}", exc_info=True)
        return hold_signal()
    
def place_stop_loss_take_profit(
    symbol,
    quantity,
    stop_loss,
    take_profit,
    position_side="Buy",
    testnet=False
):
    """
    Places conditional Stop-Loss and Take-Profit orders on Bybit, rounding prices to the symbol's tick size.

    Args:
        symbol (str): Trading pair (e.g. 'BTCUSDT').
        quantity (float): Order quantity.
        stop_loss (float): Stop-loss trigger price.
        take_profit (float): Take-profit trigger price.
        position_side (str): 'Buy' if opening long, 'Sell' if opening short position.
        testnet (bool): If True, connect to Bybit testnet.
    """
    # Initialize client
    session = HTTP(testnet=testnet)
    symbol = symbol.upper()

    # Determine category
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
    elif symbol.endswith("USDT") or symbol.endswith("USDC"):
        category = "linear"
    else:
        category = "spot"

    # Round SL and TP to tick size
    try:
        tick_size = get_tick_size(symbol, testnet=testnet)
        if tick_size and tick_size > 0:
            precision = int(abs(np.log10(tick_size)))
            stop_loss = round(stop_loss, precision)
            take_profit = round(take_profit, precision)
            print(f"Rounded Stop Loss: {stop_loss}, Rounded Take Profit: {take_profit}")
        else:
            print("Unable to fetch tick size; proceeding without rounding.")
    except Exception as e:
        print(f"Error fetching tick size: {e}")

    # Determine order sides for SL/TP
    sl_side = "Sell" if position_side.upper() == "Buy" else "Buy"
    tp_side = sl_side  # TP side is same as SL side for closing the position

    try:
        # Place Stop (SL) order
        resp_sl = session.place_conditional_order(
            category=category,
            symbol=symbol,
            side=sl_side,
            orderType="Stop",
            triggerPrice=stop_loss,
            qty=quantity,
            timeInForce="ImmediateOrCancel",
            reduceOnly=True
        )
        print(f"Stop-Loss Order Placed: {resp_sl}")

        # Place TakeProfit (TP) order
        resp_tp = session.place_conditional_order(
            category=category,
            symbol=symbol,
            side=tp_side,
            orderType="TakeProfit",
            triggerPrice=take_profit,
            qty=quantity,
            timeInForce="ImmediateOrCancel",
            reduceOnly=True
        )
        print(f"Take-Profit Order Placed: {resp_tp}")

    except (FailedRequestError, InvalidRequestError) as e:
        print(f"Bybit API error placing SL/TP orders: {e}")
    except Exception as e:
        print(f"Unexpected error in place_stop_loss_take_profit: {e}")



def get_position_details(symbol: str, testnet: bool = False):
    """
    Fetches details of an active Bybit position and computes stop_loss/take_profit levels
    with advanced risk management and contextual adjustments—identical in logic
    to the Binance version but using Bybit’s HTTP API.

    Args:
        symbol (str): Trading pair (e.g., 'ETHUSDT').
        testnet (bool): If True, connect to Bybit testnet.

    Returns:
        dict or None: Position details and computed stop_loss/take_profit, or None if no active position.
    """
    # --- Initialize Bybit session ---
    session = HTTP(
        api_key="5Z37Ko6xX1mPSIctRt",
        api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
        testnet=testnet
    )
    symbol = symbol.upper()

    # --- Determine product category ---
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        category = "inverse"
    elif symbol.endswith(("USDT", "USDC")):
        category = "linear"
    else:
        category = "spot"

    try:
        # --- Fetch Bybit positions ---
        resp = session.get_positions(category=category, symbol=symbol)
        positions = resp.get("result", {}).get("list", [])

        for pos in positions:
            size = float(pos.get("size", 0))
            api_side = pos.get("side") # "BUY" or "SELL"
            if pos.get("symbol") == symbol and api_side in ("Buy", "Sell"):
                # Basic position details
                side = api_side
                entry_price = float(pos.get("avgPrice", 0))
                quantity = size
                unrealized_profit = float(pos.get("unrealisedPnl", 0))
                leverage = float(pos.get("leverage", 0))
                logging.info(f"Fetched Leverage: {leverage}")

                # --- Fetch market data & indicators ---
                intervals = ["4h", "1h", "15m", "5m"]
                lookbacks = {
                    "4h":    "33 days ago UTC",  # ~200 × 4h
                    "1h":    "8 days ago UTC",   # ~200 × 1h
                    "15m":   "2 days ago UTC",   # ~200 × 15m
                    "5m":    "16 hours ago UTC", # ~200 × 5m
                }
                md = fetch_market_data_with_indicators(symbol, intervals, lookbacks)
                if any(interval not in md or md[interval].empty for interval in intervals):
                    print("Error: Market data for indicator calculation is unavailable.")
                    return None

                # --- Regime classification on 4h ---
                regime = classify_market_regime(md["4h"]).get("regime", "Undefined")

                # --- Extract 1h Bollinger & ATR ---
                df_1h = md["1h"]
                bollinger_lower  = df_1h["Bollinger_Lower"].iloc[-1]
                bollinger_middle = df_1h["SMA_20"].iloc[-1]
                bollinger_upper  = df_1h["Bollinger_Upper"].iloc[-1]
                atr              = df_1h["ATR_14"].iloc[-1]

                # Compute the 1/5‑bands
                delta_top_1h = (bollinger_upper  - bollinger_middle) / 5
                delta_bot_1h = (bollinger_middle - bollinger_lower)  / 5


                # Use the last fully closed candle
                prev_close = df_1h["close"].iloc[-2]

                # --- Extract 4h Bollinger ---
                df_4h = md["4h"]
                bollinger_lower_4h  = df_4h["Bollinger_Lower"].iloc[-1]
                bollinger_middle_4h = df_4h["SMA_20"].iloc[-1]
                bollinger_upper_4h  = df_4h["Bollinger_Upper"].iloc[-1]

                # Compute the 4h 1/5‑bands
                delta_top_4h = (bollinger_upper_4h  - bollinger_middle_4h) / 5
                delta_bot_4h = (bollinger_middle_4h - bollinger_lower_4h)  / 5

                if api_side == "Buy":
                    # 1h TP
                    tp_1h = bollinger_upper - delta_top_1h
                    # 4h TP
                    tp_4h = bollinger_upper_4h - delta_top_4h
                    # Fixed take-profit: choose higher
                    take_profit = max(tp_1h, tp_4h)

                    # Stop-loss logic
                    if "stop_loss" in pos and pos["stop_loss"] == (bollinger_middle - delta_bot_1h):
                        stop_loss = pos["stop_loss"]
                    else:
                        if prev_close > bollinger_middle:
                            stop_loss = bollinger_middle - delta_bot_1h
                        else:
                           stop_loss = entry_price - (take_profit - entry_price) / 3

                else:  # SELL
                    tp_1h = bollinger_lower + delta_bot_1h
                    tp_4h = bollinger_lower_4h + delta_bot_4h
                    take_profit = min(tp_1h, tp_4h)

                    if "stop_loss" in pos and pos["stop_loss"] == (bollinger_middle + delta_top_1h):
                        stop_loss = pos["stop_loss"]
                    else:
                        if prev_close < bollinger_middle:
                            stop_loss = bollinger_middle + delta_top_1h
                        else:
                            stop_loss = entry_price - (take_profit - entry_price) / 3

                logging.info(f"take_profit: {take_profit:.2f}, stop_loss: {stop_loss:.2f}")


                # --- Round to tick size ---
                tick = get_tick_size(symbol, testnet=testnet)
                if tick:
                    prec = int(abs(np.log10(tick)))
                    take_profit = round(take_profit, prec)
                    stop_loss   = round(stop_loss, prec)
                else:
                    print("Warning: Unable to fetch tick size, proceeding without rounding.")

                print(f"Final stop_loss: {stop_loss}, Final take_profit: {take_profit}")

                return {
                    "symbol": symbol,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "unrealized_profit": unrealized_profit,
                    "side": side,
                    "leverage": leverage,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "regime": regime,
                }

        print(f"No active position found for {symbol}.")
        return None

    except Exception as e:
        print(f"Unexpected error in get_position_details: {e}")
        return None



def execute_trade(
    action,
    symbol,
    quantity,
    leverage,
    trade_details,
    atr_multiplier=1.5,
    tp_multiplier=1.72,
    max_atr=200.0,
    cooldown_period=90,
    testnet=False
):
    global order_tracker

    # Initialize the session with API keys
    session = HTTP(
        api_key="5Z37Ko6xX1mPSIctRt",
        api_secret="Trl4qA9J6qWiWm455ifIQRIZibZb3oIWvjQV",
        testnet=testnet
    )
    symbol = symbol.upper()

    if not hasattr(execute_trade, 'last_trade_time'):
        execute_trade.last_trade_time = 0

    current_time = time.time()
    time_since_last_trade = current_time - execute_trade.last_trade_time

    if time_since_last_trade < cooldown_period:
        print(f"Cooldown active. {cooldown_period - time_since_last_trade:.2f} seconds remaining.")
        logger.info(f"Cooldown active. {cooldown_period - time_since_last_trade:.2f} seconds remaining.")
        return

    try:
        cancel_existing_entry_order(symbol)
    except Exception as e:
        print(f"Error cancelling entry order: {e}")
        logger.error(f"Error cancelling entry order: {e}")
        return
    
    # 1) Read current leverage
    try:
        pos = session.get_positions(
            category="linear",
            symbol=symbol
        )
        # assume there's always one entry in list for your symbol
        curr_leverage = int(pos["result"]["list"][0]["leverage"])
        logger.info(f"Current leverage on {symbol}: {curr_leverage}x")
    except Exception as e:
        logger.error("Could not fetch current leverage", exc_info=e)
        curr_leverage = None

    # 2) Only set if different
    if curr_leverage != leverage:
        try:
            resp = session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
            logger.info(f"Leverage updated on {symbol} to {leverage}x. Response: {resp}")
        except Exception as e:
            logger.error("Error setting leverage", exc_info=e)
            return
    else:
        logger.info(f"Leverage already at {leverage}x for {symbol}; skipping set_leverage.")
        
    try:
        available_margin = get_available_margin()
        combined_balance = get_combined_balance()
    except Exception as e:
        print(f"Error fetching margin: {e}")
        logger.error(f"Error fetching margin: {e}")
        return

    if available_margin < combined_balance:
        available_margin = combined_balance

    try:
        max_trade_value = available_margin * leverage * 0.95
        adjusted_quantity = max_trade_value / trade_details["Entry Price"]
    except KeyError as e:
        print(f"Missing key in trade_details: {e}")
        logger.error(f"Missing key in trade_details: {e}")
        return

    step_size = get_step_size(symbol)
    if not step_size:
        print("Invalid step size.")
        return

    adjusted_quantity = round_quantity_to_step_size(adjusted_quantity, step_size)
    min_quantity = trade_details.get("Min Quantity", 0.002)
    if adjusted_quantity < min_quantity:
        print(f"Adjusted quantity below min. Setting to {min_quantity}.")
        adjusted_quantity = min_quantity

    tick_size = get_tick_size(symbol)
    if tick_size:
        tick_precision = int(abs(np.log10(tick_size)))
        limit_price = round_price(trade_details["Entry Price"], symbol)
    else:
        limit_price = trade_details["Entry Price"]
        tick_precision = None

    current_atr = trade_details.get("ATR")
    if current_atr and current_atr > max_atr:
        print(f"ATR {current_atr} > max {max_atr}. Skipping trade.")
        return

    retries = 3
    order_quantity = adjusted_quantity
    for attempt in range(retries):
        try:
            entry_order = session.place_order(
                category="linear",
                symbol=symbol,
                side=action,
                orderType="Limit",
                qty=str(order_quantity),
                price=str(limit_price),
                timeInForce="GTC",
                reduceOnly=False
            )
            order_id = entry_order["result"]["orderId"]
            order_tracker["entry_order"] = {
                "orderId": order_id,
                "price": limit_price,
                "quantity": order_quantity,
                "side": action,
                "type": "LIMIT"
            }
            print(f"Entry order placed: {entry_order}")
            execute_trade.last_trade_time = current_time
            break
        except Exception as e:
            if "insufficient" in str(e).lower() and attempt < retries - 1:
                order_quantity *= 0.9
                order_quantity = round_quantity_to_step_size(order_quantity, step_size)
                if order_quantity < min_quantity:
                    print("Reduced quantity below minimum. Aborting.")
                    return
                time.sleep(1)
                continue
            else:
                print(f"Error placing entry order: {e}")
                return
    else:
        print("Failed to place order after retries.")
        return

    try:
        position_details = get_position_details(symbol)
        if not position_details or position_details.get("size", 0) == 0:
            print("No active position. SL/TP not placed.")
            return

        position_side = position_details.get("side", "").upper()
        if position_side not in ["Buy", "Sell"]:
            print("Invalid position side.")
            return

        stop_loss = trade_details["Stop Loss"]
        take_profit = trade_details["Take Profit"]

        if tick_precision is not None:
            stop_loss_str = f"{stop_loss:.{tick_precision}f}"
            take_profit_str = f"{take_profit:.{tick_precision}f}"
        else:
            stop_loss_str = str(stop_loss)
            take_profit_str = str(take_profit)

        sl_side = "Sell" if position_side == "Buy" else "Buy"
        tp_side = sl_side

        try:
            sl_order = session.set_trading_stop(
                category="linear",
                symbol=symbol,
                side=sl_side,
                slOrderType="Limit",
                qty=str(order_quantity),
                stopLoss=stop_loss_str,
                reduceOnly=True
            )
            order_tracker["stop_loss_order"] = {"orderId": sl_order["result"]["orderId"], "price": stop_loss}
            print(f"SL Order: {sl_order}")
        except Exception as e:
            print(f"Error placing SL: {e}")

        try:
            tp_order = session.set_trading_stop(
                category="linear",
                symbol=symbol,
                side=tp_side,
                tpOrderType="Limit",
                qty=str(order_quantity),
                takeProfit=take_profit_str,
                reduceOnly=True
            )
            order_tracker["take_profit_order"] = {"orderId": tp_order["result"]["orderId"], "price": take_profit}
            print(f"TP Order: {tp_order}")
        except Exception as e:
            print(f"Error placing TP: {e}")

    except Exception as e:
        print(f"Error retrieving position: {e}")

    
## main trading loop *****




def trading_loop(symbol=pair, starting_balance=25):
    """
    Main trading loop for continuous monitoring and trading.
    Incorporates probability model to dynamically adjust trade signals and includes a ratchet mechanism.
    Data fetch aligns exactly to the top of each UTC minute.
    """

    global order_tracker, last_update_time
    order_tracker = {
        "entry_order": None,
        "stop_loss_order": None,
        "take_profit_order": None,
    }
    last_update_time = {}
    last_regime = None
    long_model  = long_run["model"]     
    short_model = short_run["model"]     



    while True:
        try:
            logging.info("=== Starting New Loop ===")

            # 1) Ensure no conflicting positions
            if not check_no_open_orders_and_positions(symbol):
                logging.info("Open orders/positions elsewhere; waiting 1m")
                time.sleep(60)
                continue

            # 2) Wallet & profit
            combined_balance = get_combined_balance()
            logging.info(f"Combined Balance: {combined_balance:.2f}")
            profit = combined_balance - starting_balance
            profit_pct = (profit / starting_balance) * 100 if starting_balance else 0
            logging.info(f"Profit: {profit:.2f} USDT ({profit_pct:.2f}%)")
            if combined_balance <= 0:
                logging.warning("Insufficient balance; exiting loop.")
                break

            # 3) ETA to $1M (optional)
            ttm = calculate_time_to_million(
                symbol=symbol,
                starting_balance=combined_balance,
                target_balance=1_000_000,
                lookback_days=14
            )
            if ttm is not None:
                logging.info(f"Estimated days to $1M: {ttm:.2f}")

            # 4) Clean up any filled orders
            monitor_order_fulfillment(symbol)

            # 5) Align to top of the next UTC minute
            now = datetime.now(timezone.utc)
            sleep_sec = 60 - now.second - now.microsecond / 1e6
            if sleep_sec > 0:
                logging.info(f"Sleeping {sleep_sec:.2f}s for minute-aligned fetch")
                time.sleep(sleep_sec)

            # 6) Fetch & debug-dump market data
            intervals = ["4h", "1h", "15m", "5m", "1d"]

            lookback_periods = {
                "4h":  "36 days ago UTC",
                "1h":  "10 days ago UTC",
                "15m": "3 days ago UTC",
                "5m":  "20 hours ago UTC",
                "1d":  "220 days ago UTC",
            }
            market_data_dict = fetch_market_data_with_indicators(
                symbol, intervals, lookback_periods
            )

            # Debug CSV
            debug_dir = os.path.join(os.path.dirname(__file__), "debug_csv")
            os.makedirs(debug_dir, exist_ok=True)
            for iv, df in market_data_dict.items():
                if df is not None and not df.empty:
                    fn = os.path.join(debug_dir, f"{iv}-{symbol}-bybit-data-debug.csv")
                    df.to_csv(fn, index=False)
                    logging.info(f"Saved {iv} data → {fn}")
                else:
                    logging.warning(f"{iv} data empty or None; skipped CSV.")

            # 7) Unpack for downstream
            m4h  = market_data_dict.get("4h")
            m1h  = market_data_dict.get("1h")
            m15m = market_data_dict.get("15m")
            m5m  = market_data_dict.get("5m")
            m1d  = market_data_dict.get("1d")

            # Must have 4h to proceed
            if m4h is None or m4h.empty:
                logging.warning("4h data missing; retrying in 15s")
                time.sleep(15)
                continue

            # 8) Regime classification
            try:
                regime_info = classify_market_regime(m4h)
                regime        = regime_info.get("regime", "Undefined")
                regime_change = regime_info.get("regime_change", False)
                logging.info(f"4h regime: {regime_info}")
            except Exception as e:
                logging.error("Regime classification error", exc_info=True)
                time.sleep(15)
                continue

            m4h["Regime"] = regime
            if m1h is not None:
                m1h["Regime"] = regime

            if regime_change:
                logging.info(f"Regime changed {last_regime} → {regime}")
                last_regime = regime

            # 9) Position handling
            if has_active_position(symbol):
                logging.info(f"Active position on {symbol}")
                pos = get_position_details(symbol)
                if pos:
                    logging.info(f"Position details: {pos}")
                    validated = classify_market_regime(m4h).get("regime","Undefined")
                    logging.info(f"Validated regime: {validated}, side: {pos['side']}")
                    place_or_update_sl_tp_orders(
                        symbol, pos, pos.get("stop_loss"), pos.get("take_profit")
                    )
                else:
                    logging.error("Missing position details")
                time.sleep(15)
                continue
            else:
                cancel_all_sl_tp_orders(symbol)

            # 10) Generate & execute signal
            sig = generate_trade_signal(
                    m1h, m4h, m5m, m15m, m1d,
                    regime,
                    regime_change=regime_change,
                    symbol=symbol,
                    long_model=long_model,     # legacy param (ignored)
                    short_model=short_model,   # legacy param (ignored)
                    long_run=long_run,         # <-- used
                    short_run=short_run,       # <-- used
            )
            logging.info(f"Trade signal: {sig}")

            if sig["action"] != "HOLD":
                trade_qty = calculate_trade_quantity(
                    wallet_balance=combined_balance,
                    leverage=sig["leverage"],
                    entry_price=sig["entry_price"]
                )
                if trade_qty is None:
                    logging.warning("Qty calc failed; skipping trade")
                    time.sleep(15)
                else:
                    logging.info(f"Executing {sig['action']} @ {sig['entry_price']}")
                    execute_trade(
                        action=sig["action"],
                        symbol=symbol,
                        quantity=trade_qty,
                        leverage=sig["leverage"],
                        trade_details={
                            "Entry Price": sig["entry_price"],
                            "Stop Loss":  sig["stop_loss"],
                            "Take Profit":sig["take_profit"],
                        }
                    )
            else:
                logging.info("Signal=HOLD; cancelling any open entry orders")
                cancel_existing_entry_order(symbol)

            logging.debug(f"Order tracker: {order_tracker}")
            time.sleep(15)

        except (FailedRequestError, InvalidRequestError) as api_err:
            logging.error("Bybit API error", exc_info=True)
            time.sleep(15)
        except Exception as e:
            logging.error("Unexpected error in trading loop", exc_info=True)
            time.sleep(15)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    trading_loop()
