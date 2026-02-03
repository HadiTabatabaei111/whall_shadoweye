#!/usr/bin/env python3
"""
══════════════════════════════════════════════════════════════════════════════
   🐋 Whale Hunter Pro v6.0 - سیستم جامع رصد نهنگ مادر و اتو ترید
   
   ✅ رصد نهنگ مادر ($500K+)
   ✅ اعتبارسنجی 3 مرحله‌ای (1، 2، 4 دقیقه)
   ✅ پامپ/دامپ با وزن بالا
   ✅ RSI, MACD, Volume, OHLCV
   ✅ دیتابیس sqlite3
   ✅ داشبورد کنترلی + داشبورد اتوترید
   ✅ اتصال به LBank و Bitunix
   
   برای اجرا:
   pip install flask requests
   python whale_hunter.py
══════════════════════════════════════════════════════════════════════════════
"""
from flask import Flask, render_template_string, jsonify, send_file, request
import requests
import sqlite3
import hmac
import hashlib
import time
import json
import threading
from datetime import datetime, timedelta
from collections import deque
import os
import logging

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# تنظیمات پارامتریک (قابل تغییر از داشبورد)
# ═══════════════════════════════════════════════════════════════════════════

CONFIG = {
    # API
    "api_source": "coingecko",  # coingecko, kucoin, bybit
    "api_source_sync": True,  # هماهنگ کردن انتخاب صرافی بین بک‌اند و فرانت
    "update_interval": 2,  # کاهش زمان بروزرسانی برای سرعت بالاتر (قبلاً 10 بود)
    "market_cache_ttl": 5,  # زمان cache برای دیتای بازار (ثانیه) - برای سرعت بیشتر
    
    # نهنگ
    "whale_threshold": 500000,  # دلار
    "pump_dump_threshold": 3,  # درصد
    "pump_dump_time": 1,  # دقیقه (پارامتریک)
    "pump_dump_weight": 80,  # وزن پامپ/دامپ معتبر
    
    # اعتبارسنجی (پارامتریک - قابل تغییر)
    "validation_times": [1, 2, 4],  # دقیقه (مراحل اعتبارسنجی)
    "validation_weights": [20, 30, 50],  # درصد (وزن هر مرحله - باید مجموع 100 باشد)
    "min_price_change": 0.1,  # حداقل تغییر قیمت
    
    # اندیکاتورها
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    
    # اتوترید
    "trade_amount": 5,  # دلار
    "leverage": 5,
    "stop_loss": 2,  # درصد
    "take_profit": 4,  # درصد
    "commission": 0.05,  # درصد
    "max_daily_trades": 4,
    "max_consecutive_losses": 4,
    "min_score_for_trade": 70,
    
    # صرافی
    "exchange": "lbank",
    "api_key": "",
    "secret_key": "",
}

# ═══════════════════════════════════════════════════════════════════════════
# دیتابیس sqlite3
# ═══════════════════════════════════════════════════════════════════════════

DB_PATH = "whale_hunter.db"

def init_db():
    """ایجاد جداول دیتابیس"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # جدول نهنگ‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS whales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        price REAL NOT NULL,
        volume REAL NOT NULL,
        change_percent REAL,
        whale_type TEXT,
        is_real INTEGER DEFAULT 1,
        confidence_score REAL DEFAULT 0,
        pattern TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # جدول سیگنال‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        entry_price REAL NOT NULL,
        price_1min REAL,
        price_2min REAL,
        price_4min REAL,
        change_1min REAL,
        change_2min REAL,
        change_4min REAL,
        valid_1min INTEGER DEFAULT 0,
        valid_2min INTEGER DEFAULT 0,
        valid_4min INTEGER DEFAULT 0,
        final_status TEXT DEFAULT 'pending',
        score INTEGER DEFAULT 0,
        source TEXT,
        rsi REAL,
        macd REAL,
        macd_signal REAL,
        macd_histogram REAL,
        volume REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        validated_at DATETIME
    )''')
    
    # جدول پامپ/دامپ
    c.execute('''CREATE TABLE IF NOT EXISTS pump_dumps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        event_type TEXT NOT NULL,
        price_before REAL NOT NULL,
        price_after REAL NOT NULL,
        change_percent REAL NOT NULL,
        volume REAL,
        is_valid INTEGER DEFAULT 0,
        validation_price REAL,
        score INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        validated_at DATETIME
    )''')
    
    # جدول معاملات
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id INTEGER,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        entry_price REAL NOT NULL,
        exit_price REAL,
        amount REAL NOT NULL,
        leverage INTEGER DEFAULT 1,
        pnl REAL DEFAULT 0,
        pnl_percent REAL DEFAULT 0,
        commission REAL DEFAULT 0,
        net_pnl REAL DEFAULT 0,
        status TEXT DEFAULT 'open',
        stop_loss REAL,
        take_profit REAL,
        exchange TEXT,
        order_id TEXT,
        opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        closed_at DATETIME
    )''')
    
    # جدول OHLCV
    c.execute('''CREATE TABLE IF NOT EXISTS ohlcv (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timeframe TEXT DEFAULT '1m',
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # جدول اندیکاتورها
    c.execute('''CREATE TABLE IF NOT EXISTS indicators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        rsi REAL,
        macd REAL,
        macd_signal REAL,
        macd_histogram REAL,
        ema_20 REAL,
        ema_50 REAL,
        volume_avg REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # جدول تنظیمات
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # جدول گزارشات
    c.execute('''CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_type TEXT,
        date TEXT,
        total_trades INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        total_pnl REAL DEFAULT 0,
        total_commission REAL DEFAULT 0,
        net_pnl REAL DEFAULT 0,
        win_rate REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # ایجاد ایندکس‌ها برای افزایش سرعت
    c.execute('CREATE INDEX IF NOT EXISTS idx_whales_symbol ON whales(symbol)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_whales_timestamp ON whales(timestamp)')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(final_status)')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_pump_symbol ON pump_dumps(symbol)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_pump_timestamp ON pump_dumps(timestamp)')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(opened_at)')
    
    conn.commit()
    conn.close()
    print("✅ دیتابیس آماده شد (ایندکس‌گذاری شد)")

# ═══════════════════════════════════════════════════════════════════════════
# کلاس‌های اصلی
# ═══════════════════════════════════════════════════════════════════════════

class PriceHistory:
    """ذخیره تاریخچه قیمت برای محاسبه اندیکاتورها"""
    def __init__(self, max_size=100):
        self.data = {}
        self.max_size = max_size
    
    def add(self, symbol, price, volume):
        if symbol not in self.data:
            self.data[symbol] = deque(maxlen=self.max_size)
        self.data[symbol].append({
            'price': price,
            'volume': volume,
            'time': datetime.now()
        })
    
    def get(self, symbol, count=14):
        if symbol not in self.data:
            return []
        return list(self.data[symbol])[-count:]

price_history = PriceHistory()

class Indicators:
    """محاسبه اندیکاتورها"""
    
    @staticmethod
    def calculate_rsi(prices, period=14):
        if len(prices) < period + 1:
            return None
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        if len(gains) < period:
            return None
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    
    @staticmethod
    def calculate_macd(prices, fast=12, slow=26, signal=9):
        if len(prices) < slow:
            return None, None, None
        
        def ema(data, period):
            multiplier = 2 / (period + 1)
            ema_val = data[0]
            for price in data[1:]:
                ema_val = (price - ema_val) * multiplier + ema_val
            return ema_val
        
        ema_fast = ema(prices[-fast:], fast)
        ema_slow = ema(prices[-slow:], slow)
        macd_line = ema_fast - ema_slow
        
        # برای سیگنال نیاز به تاریخچه MACD داریم
        signal_line = macd_line * 0.9  # ساده‌سازی
        histogram = macd_line - signal_line
        
        return round(macd_line, 4), round(signal_line, 4), round(histogram, 4)
    
    @staticmethod
    def calculate_all(symbol):
        history = price_history.get(symbol, 30)
        if len(history) < 14:
            return {}
        
        prices = [h['price'] for h in history]
        volumes = [h['volume'] for h in history]
        
        rsi = Indicators.calculate_rsi(prices)
        macd, macd_sig, macd_hist = Indicators.calculate_macd(prices)
        
        result = {
            'rsi': rsi,
            'macd': macd,
            'macd_signal': macd_sig,
            'macd_histogram': macd_hist,
            'volume_avg': sum(volumes) / len(volumes) if volumes else 0,
            'ema_20': sum(prices[-20:]) / min(len(prices), 20) if prices else 0,
        }
        
        # ذخیره در دیتابیس
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO indicators (symbol, rsi, macd, macd_signal, macd_histogram, ema_20, volume_avg)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (symbol, result['rsi'], result['macd'], result['macd_signal'], 
                   result['macd_histogram'], result['ema_20'], result['volume_avg']))
        conn.commit()
        conn.close()
        
        return result

class MarketAPI:
    """دریافت قیمت از API"""
    
    session = requests.Session()
    
    @staticmethod
    def fetch_coingecko():
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "sparkline": False,
                "price_change_percentage": "1h,24h"
            }
            # استفاده از Session برای سرعت بیشتر
            response = MarketAPI.session.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [{
                    'symbol': f"{item['symbol'].upper()}USDT",
                    'price': item['current_price'],
                    'change_24h': item.get('price_change_percentage_24h', 0) or 0,
                    'change_1h': item.get('price_change_percentage_1h_in_currency', 0) or 0,
                    'high_24h': item.get('high_24h', 0),
                    'low_24h': item.get('low_24h', 0),
                    'volume': item.get('total_volume', 0),
                    'market_cap': item.get('market_cap', 0),
                } for item in data]
        except Exception as e:
            print(f"❌ CoinGecko Error: {e}")
        return None
    
    @staticmethod
    def fetch_kucoin():
        try:
            url = "https://api.kucoin.com/api/v1/market/allTickers"
            response = MarketAPI.session.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                tickers = data.get('data', {}).get('ticker', [])
                return [{
                    'symbol': t['symbol'].replace('-', ''),
                    'price': float(t.get('last', 0)),
                    'change_24h': float(t.get('changeRate', 0)) * 100,
                    'change_1h': 0,
                    'high_24h': float(t.get('high', 0)),
                    'low_24h': float(t.get('low', 0)),
                    'volume': float(t.get('volValue', 0)),
                    'market_cap': 0,
                } for t in tickers if t['symbol'].endswith('-USDT')][:100]
        except Exception as e:
            print(f"❌ KuCoin Error: {e}")
        return None
    
    @staticmethod
    def fetch_bybit():
        try:
            url = "https://api.bybit.com/v5/market/tickers"
            params = {"category": "spot"}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                tickers = data.get('result', {}).get('list', [])
                return [{
                    'symbol': t['symbol'],
                    'price': float(t.get('lastPrice', 0)),
                    'change_24h': float(t.get('price24hPcnt', 0)) * 100,
                    'change_1h': 0,
                    'high_24h': float(t.get('highPrice24h', 0)),
                    'low_24h': float(t.get('lowPrice24h', 0)),
                    'volume': float(t.get('turnover24h', 0)),
                    'market_cap': 0,
                } for t in tickers if t['symbol'].endswith('USDT')][:100]
        except Exception as e:
            print(f"❌ Bybit Error: {e}")
        return None
    
    # Cache برای سرعت بیشتر (غیرفعال شده برای دیتای fresh)
    _cache = {}
    _cache_time = {}
    
    @staticmethod
    def fetch(source=None):
        source = source or CONFIG['api_source']
        # Cache غیرفعال شده - همیشه دیتای fresh بگیر
        # cache_ttl = CONFIG.get('market_cache_ttl', 5)
        
        # بررسی cache (غیرفعال)
        # cache_key = f"market_{source}"
        # now = time.time()
        # if cache_key in MarketAPI._cache and cache_key in MarketAPI._cache_time:
        #     if now - MarketAPI._cache_time[cache_key] < cache_ttl:
        #         return MarketAPI._cache[cache_key]
        
        # دریافت دیتا
        if source == 'coingecko':
            data = MarketAPI.fetch_coingecko()
        elif source == 'kucoin':
            data = MarketAPI.fetch_kucoin()
        elif source == 'bybit':
            data = MarketAPI.fetch_bybit()
        else:
            data = None
        
        if data:
            # حذف تکرارها بر اساس symbol (برای رفع مشکل ارزهای تکراری)
            seen = {}
            unique_data = []
            for item in data:
                symbol = item['symbol']
                if symbol not in seen or item.get('volume', 0) > seen[symbol].get('volume', 0):
                    if symbol in seen:
                        # جایگزین با داده بهتر
                        idx = unique_data.index(seen[symbol])
                        unique_data[idx] = item
                    else:
                        unique_data.append(item)
                    seen[symbol] = item
            
            data = unique_data
            
            # ذخیره در تاریخچه و OHLCV (بهینه شده - batch insert)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            batch_data = []
            for item in data:
                price_history.add(item['symbol'], item['price'], item['volume'])
                batch_data.append((
                    item['symbol'], item['price'], item.get('high_24h', item['price']), 
                    item.get('low_24h', item['price']), item['price'], item['volume']
                ))
            
            # Batch insert برای سرعت بیشتر
            if batch_data:
                c.executemany('''INSERT INTO ohlcv (symbol, open, high, low, close, volume)
                                 VALUES (?, ?, ?, ?, ?, ?)''', batch_data)
            conn.commit()
            conn.close()
            
            # Cache غیرفعال - همیشه دیتای fresh
            # MarketAPI._cache[cache_key] = data
            # MarketAPI._cache_time[cache_key] = now
        
        return data

class SignalValidator:
    """اعتبارسنجی سیگنال‌ها"""
    
    pending_signals = {}  # {signal_id: signal_data}
    pending_pumps = {}  # {pump_id: pump_data}
    
    @staticmethod
    def validate_signal(signal_id, signal_type, entry_price, current_price, stage):
        """
        اعتبارسنجی:
        - LONG + قیمت بالا رفت → معتبر
        - SHORT + قیمت پایین آمد → معتبر
        - مخالف → نامعتبر
        """
        change = ((current_price - entry_price) / entry_price) * 100
        min_change = CONFIG['min_price_change']
        
        if signal_type == 'LONG':
            is_valid = change >= min_change
        else:  # SHORT
            is_valid = change <= -min_change
        
        return {
            'is_valid': is_valid,
            'change': round(change, 4),
            'price': current_price,
            'stage': stage
        }
    
    @staticmethod
    def calculate_score(validations):
        """
        محاسبه امتیاز نهایی با وزن‌های دقیق
        کنترل نهایی: فقط مراحل معتبر امتیاز می‌گیرند
        """
        weights = CONFIG['validation_weights']
        score = 0
        total_weight = sum(weights)
        
        # محاسبه امتیاز بر اساس وزن‌ها
        for i, v in enumerate(validations):
            if v and v.get('is_valid'):
                if i < len(weights):
                    score += weights[i]
        
        # نرمال‌سازی به 100 (اگر وزن‌ها 100 نباشند)
        if total_weight != 100:
            score = int((score / total_weight) * 100) if total_weight > 0 else 0
        
        return min(score, 100)  # حداکثر 100
    
    @staticmethod
    def add_pending_signal(signal_id, symbol, signal_type, entry_price):
        """افزودن سیگنال به لیست انتظار"""
        SignalValidator.pending_signals[signal_id] = {
            'symbol': symbol,
            'signal_type': signal_type,
            'entry_price': entry_price,
            'created_at': datetime.now(),
            'validations': [None, None, None]
        }
    
    @staticmethod
    def check_pending_signals(market_data):
        """بررسی سیگنال‌های در انتظار"""
        price_map = {item['symbol']: item['price'] for item in market_data}
        validation_times = CONFIG['validation_times']
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        for signal_id, signal in list(SignalValidator.pending_signals.items()):
            symbol = signal['symbol']
            if symbol not in price_map:
                continue
            
            current_price = price_map[symbol]
            elapsed = (datetime.now() - signal['created_at']).total_seconds() / 60
            
            # بررسی هر مرحله اعتبارسنجی (با timing دقیق و به موقع)
            for i, minutes in enumerate(validation_times):
                # بررسی دقیق: اگر زمان رسیده (با tolerance 0.1 دقیقه) و هنوز اعتبارسنجی نشده
                # این باعث می‌شود اعتبارسنجی به موقع انجام شود
                time_tolerance = 0.1  # 6 ثانیه tolerance
                if elapsed >= (minutes - time_tolerance) and signal['validations'][i] is None:
                    result = SignalValidator.validate_signal(
                        signal_id,
                        signal['signal_type'],
                        signal['entry_price'],
                        current_price,
                        i + 1
                    )
                    signal['validations'][i] = result
                    
                    # بروزرسانی دیتابیس با نام فیلدهای صحیح
                    # استفاده از نام‌های ثابت: price_1min, price_2min, price_4min
                    if minutes == 1:
                        field = "price_1min"
                        change_field = "change_1min"
                        valid_field = "valid_1min"
                    elif minutes == 2:
                        field = "price_2min"
                        change_field = "change_2min"
                        valid_field = "valid_2min"
                    elif minutes == 4:
                        field = "price_4min"
                        change_field = "change_4min"
                        valid_field = "valid_4min"
                    else:
                        # برای زمان‌های دیگر از نام پویا استفاده کن
                        field = f"price_{minutes}min"
                        change_field = f"change_{minutes}min"
                        valid_field = f"valid_{minutes}min"
                    
                    c.execute(f'''UPDATE signals SET 
                                  {field} = ?, {change_field} = ?, {valid_field} = ?
                                  WHERE id = ?''',
                              (current_price, result['change'], 
                               1 if result['is_valid'] else 0, signal_id))
                    
                    print(f"⏱️ اعتبارسنجی مرحله {i+1} ({minutes} دقیقه): {signal['symbol']} - {'✅ معتبر' if result['is_valid'] else '❌ نامعتبر'} (تغییر: {result['change']:.2f}%)")
            
            # کنترل نهایی: اگر همه مراحل تکمیل شد
            if all(v is not None for v in signal['validations']):
                # محاسبه امتیاز با وزن‌های دقیق
                score = SignalValidator.calculate_score(signal['validations'])
                valid_count = sum(1 for v in signal['validations'] if v and v['is_valid'])
                
                # کنترل نهایی: حداقل 2 مرحله باید معتبر باشد
                final_status = 'valid' if valid_count >= 2 else 'invalid'
                
                # بروزرسانی دیتابیس
                c.execute('''UPDATE signals SET 
                             final_status = ?, score = ?, validated_at = ?
                             WHERE id = ?''',
                          (final_status, score, datetime.now(), signal_id))
                
                # لاگ کنترل نهایی
                print(f"🎯 کنترل نهایی اعتبارسنجی: {signal['symbol']} {signal['signal_type']}")
                print(f"   - مراحل معتبر: {valid_count}/3")
                print(f"   - امتیاز نهایی: {score} (وزن‌ها: {CONFIG['validation_weights']})")
                print(f"   - وضعیت: {final_status}")
                
                # اگر معتبر بود و امتیاز کافی داشت، به صف اتوترید اضافه کن
                if final_status == 'valid' and score >= CONFIG['min_score_for_trade']:
                    print(f"✅ سیگنال معتبر برای اتوترید: {signal['symbol']} {signal['signal_type']} (امتیاز: {score})")
                    # سیگنال در صف قرار می‌گیرد و در background_worker بررسی می‌شود
                elif final_status == 'valid' and score < CONFIG['min_score_for_trade']:
                    print(f"⚠️ سیگنال معتبر اما امتیاز ناکافی: {signal['symbol']} (امتیاز: {score} < {CONFIG['min_score_for_trade']})")
                
                del SignalValidator.pending_signals[signal_id]
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def add_pending_pump(pump_id, symbol, event_type, price):
        """افزودن پامپ/دامپ به لیست انتظار"""
        SignalValidator.pending_pumps[pump_id] = {
            'symbol': symbol,
            'event_type': event_type,
            'entry_price': price,
            'created_at': datetime.now()
        }
    
    @staticmethod
    def check_pending_pumps(market_data):
        """بررسی پامپ/دامپ‌های در انتظار (1 دقیقه)"""
        price_map = {item['symbol']: item['price'] for item in market_data}
        pump_time = CONFIG['pump_dump_time']
        pump_weight = CONFIG['pump_dump_weight']
        min_change = CONFIG['min_price_change']
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        for pump_id, pump in list(SignalValidator.pending_pumps.items()):
            symbol = pump['symbol']
            if symbol not in price_map:
                continue
            
            current_price = price_map[symbol]
            elapsed = (datetime.now() - pump['created_at']).total_seconds() / 60
            
            if elapsed >= pump_time:
                change = ((current_price - pump['entry_price']) / pump['entry_price']) * 100
                
                # پامپ معتبر = قیمت بالا رفت
                # دامپ معتبر = قیمت پایین آمد
                if pump['event_type'] == 'pump':
                    is_valid = change >= min_change
                else:
                    is_valid = change <= -min_change
                
                score = pump_weight if is_valid else 0
                
                c.execute('''UPDATE pump_dumps SET 
                             is_valid = ?, validation_price = ?, score = ?, validated_at = ?
                             WHERE id = ?''',
                          (1 if is_valid else 0, current_price, score, datetime.now(), pump_id))
                
                # اگر معتبر بود، سیگنال ایجاد کن
                if is_valid and score >= CONFIG['min_score_for_trade']:
                    signal_type = 'LONG' if pump['event_type'] == 'pump' else 'SHORT'
                    c.execute('''INSERT INTO signals 
                                 (symbol, signal_type, entry_price, final_status, score, source, validated_at)
                                 VALUES (?, ?, ?, 'valid', ?, 'pump_dump', ?)''',
                              (symbol, signal_type, current_price, score, datetime.now()))
                    print(f"✅ پامپ/دامپ معتبر: {symbol} {signal_type} (امتیاز: {score}) - به صف اتوترید اضافه شد")
                
                del SignalValidator.pending_pumps[pump_id]
        
        conn.commit()
        conn.close()

class WhaleDetector:
    """تشخیص نهنگ و پامپ/دامپ"""
    
    previous_prices = {}
    
    @staticmethod
    def detect(market_data):
        whales = []
        pump_dumps = []
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        for item in market_data:
            symbol = item['symbol']
            price = item['price']
            volume = item['volume']
            change = item.get('change_24h', 0)
            
            # تشخیص نهنگ (حجم بالای $500K)
            if volume >= CONFIG['whale_threshold']:
                whale_type = 'buy' if change > 0 else 'sell'
                
                # تشخیص الگو (نوک‌زدن به طعمه)
                pattern = None
                if symbol in WhaleDetector.previous_prices:
                    prev = WhaleDetector.previous_prices[symbol]
                    quick_change = ((price - prev) / prev) * 100
                    if abs(quick_change) > 5:
                        pattern = 'bait_pecking'  # نوک‌زدن به طعمه
                
                # امتیاز اعتبار نهنگ
                confidence = min(100, (volume / CONFIG['whale_threshold']) * 50 + abs(change) * 5)
                
                c.execute('''INSERT INTO whales 
                             (symbol, price, volume, change_percent, whale_type, confidence_score, pattern)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                          (symbol, price, volume, change, whale_type, confidence, pattern))
                
                whale_id = c.lastrowid
                whales.append({
                    'id': whale_id,
                    'symbol': symbol,
                    'price': price,
                    'volume': volume,
                    'change': change,
                    'type': whale_type,
                    'confidence': confidence,
                    'pattern': pattern
                })
                
                # ایجاد سیگنال از نهنگ
                signal_type = 'LONG' if whale_type == 'buy' else 'SHORT'
                indicators = Indicators.calculate_all(symbol)
                
                c.execute('''INSERT INTO signals 
                             (symbol, signal_type, entry_price, source, rsi, macd, macd_signal, macd_histogram, volume)
                             VALUES (?, ?, ?, 'whale', ?, ?, ?, ?, ?)''',
                          (symbol, signal_type, price, 
                           indicators.get('rsi'), indicators.get('macd'),
                           indicators.get('macd_signal'), indicators.get('macd_histogram'),
                           volume))
                
                signal_id = c.lastrowid
                SignalValidator.add_pending_signal(signal_id, symbol, signal_type, price)
            
            # تشخیص پامپ/دامپ
            if symbol in WhaleDetector.previous_prices:
                prev_price = WhaleDetector.previous_prices[symbol]
                quick_change = ((price - prev_price) / prev_price) * 100
                
                if abs(quick_change) >= CONFIG['pump_dump_threshold']:
                    event_type = 'pump' if quick_change > 0 else 'dump'
                    
                    c.execute('''INSERT INTO pump_dumps 
                                 (symbol, event_type, price_before, price_after, change_percent, volume)
                                 VALUES (?, ?, ?, ?, ?, ?)''',
                              (symbol, event_type, prev_price, price, quick_change, volume))
                    
                    pump_id = c.lastrowid
                    pump_dumps.append({
                        'id': pump_id,
                        'symbol': symbol,
                        'type': event_type,
                        'change': quick_change,
                        'price': price
                    })
                    
                    SignalValidator.add_pending_pump(pump_id, symbol, event_type, price)
            
            WhaleDetector.previous_prices[symbol] = price
        
        conn.commit()
        conn.close()
        
        return whales, pump_dumps

class LBankAPI:
    """کلاس مدیریت API صرافی LBank"""
    BASE_URL = "https://api.lbank.info"
    session = requests.Session()
    
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key
        
    def _sign(self, params):
        """تولید امضای دیجیتال"""
        # حذف پارامترهای خالی
        params = {k: v for k, v in params.items() if v is not None}
        # مرتب‌سازی بر اساس کلید
        sorted_params = sorted(params.items())
        # ساخت رشته کوئری
        query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
        # تولید امضا با HMAC SHA256
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature.upper()

    def create_order(self, symbol, side, order_type, price, amount):
        """ایجاد سفارش جدید"""
        try:
            path = "/v2/create_order.do"
            url = f"{self.BASE_URL}{path}"
            
            # تبدیل نماد به فرمت LBank (مثلاً btc_usdt)
            symbol = symbol.lower().replace('/', '_')
            if '_' not in symbol and 'usdt' in symbol:
                 symbol = symbol.replace('usdt', '_usdt')

            timestamp = str(int(time.time() * 1000))
            
            # نوع سفارش در LBank: buy, sell, buy_market, sell_market
            type_str = side.lower()
            if order_type == 'market':
                type_str += '_market'
            
            params = {
                'api_key': self.api_key,
                'symbol': symbol,
                'type': type_str,
                'price': str(price),
                'amount': str(amount),
                'timestamp': timestamp
            }
            
            params['sign'] = self._sign(params)
            
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            # استفاده از session برای سرعت بالاتر
            response = LBankAPI.session.post(url, data=params, headers=headers, timeout=5)
            return response.json()
            
        except Exception as e:
            logging.error(f"LBank Order Error: {e}")
            return {'result': 'false', 'error_code': str(e)}

class AutoTrader:
    """اتو ترید"""
   #    """اتو ////////////////////////////"""  
    is_running = True
    daily_trades = 0
    consecutive_losses = 0
    last_trade_date = None
    open_trades = {}
    session = requests.Session()
    
    @staticmethod
    def get_account_info():
        """دریافت اطلاعات حساب"""
        exchange = CONFIG['exchange']
        api_key = CONFIG['api_key']
        secret_key = CONFIG['secret_key']
        
        if not api_key or not secret_key:
            return {'success': False, 'error': 'API Keys not set'}
        
        try:
            if exchange == 'lbank':
                url = "https://api.lbank.info/v2/user_info.do"
                timestamp = str(int(time.time() * 1000))
                params = {'api_key': api_key, 'timestamp': timestamp}
                
                # امضا
                sign_str = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
                signature = hmac.new(secret_key.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
                params['sign'] = signature
                
                # استفاده از session
                response = AutoTrader.session.post(url, data=params, timeout=5)
                data = response.json()
                
                if data.get('result') == 'true':
                    info = data.get('info', {})
                    usdt = info.get('free', {}).get('usdt', 0)
                    return {
                        'success': True,
                        'exchange': 'LBank',
                        'name': f"LBank_{api_key[:6]}",
                        'uid': api_key[:12],
                        'balance': float(usdt),
                        'available': float(usdt),
                        'locked': 0
                    }
                else:
                    return {'success': False, 'error': data.get('error_code', 'Unknown')}
            
            elif exchange == 'bitunix':
                url = "https://api.bitunix.com/api/v1/account"
                timestamp = str(int(time.time() * 1000))
                params = {'apiKey': api_key, 'timestamp': timestamp}
                
                sign_str = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
                signature = hmac.new(secret_key.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
                params['signature'] = signature
                
                # استفاده از session
                response = AutoTrader.session.get(url, params=params, timeout=5)
                data = response.json()
                
                if data.get('code') == 0:
                    info = data.get('data', {})
                    return {
                        'success': True,
                        'exchange': 'Bitunix',
                        'name': info.get('username', f"Bitunix_{api_key[:6]}"),
                        'uid': info.get('uid', api_key[:12]),
                        'balance': float(info.get('balance', 0)),
                        'available': float(info.get('available', 0)),
                        'locked': float(info.get('locked', 0))
                    }
                else:
                    return {'success': False, 'error': data.get('msg', 'Unknown')}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'Unknown exchange'}
    
    @staticmethod
    def can_trade():
        """بررسی امکان معامله"""
        today = datetime.now().date()
        
        if AutoTrader.last_trade_date != today:
            AutoTrader.daily_trades = 0
            AutoTrader.consecutive_losses = 0
            AutoTrader.last_trade_date = today
        
        if AutoTrader.daily_trades >= CONFIG['max_daily_trades']:
            return False, "حداکثر معاملات روزانه"
        
        if AutoTrader.consecutive_losses >= CONFIG['max_consecutive_losses']:
            return False, "ضررهای متوالی - توقف"
        
        return True, "OK"
    
    @staticmethod
    def get_trade_queue():
        """دریافت صف اتوترید (مرتب بر امتیاز)"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''SELECT * FROM signals 
                     WHERE final_status = 'valid' AND score >= ?
                     ORDER BY score DESC
                     LIMIT 20''', (CONFIG['min_score_for_trade'],))
        
        columns = [desc[0] for desc in c.description]
        signals = [dict(zip(columns, row)) for row in c.fetchall()]
        
        conn.close()
        return signals
    
    @staticmethod
    def execute_trade(signal):
        """اجرای معامله"""
        can, reason = AutoTrader.can_trade()
        if not can:
            return {'success': False, 'error': reason}
        
        symbol = signal['symbol']
        side = signal['signal_type']
        entry_price = signal['entry_price']
        amount = CONFIG['trade_amount']
        leverage = CONFIG['leverage']
        
        # محاسبه SL و TP
        if side == 'LONG':
            stop_loss = entry_price * (1 - CONFIG['stop_loss'] / 100)
            take_profit = entry_price * (1 + CONFIG['take_profit'] / 100)
        else:
            stop_loss = entry_price * (1 + CONFIG['stop_loss'] / 100)
            take_profit = entry_price * (1 - CONFIG['take_profit'] / 100)
        
        # اجرای سفارش در صرافی واقعی
        exchange_order_id = "SIMULATED"
        if CONFIG['exchange'] == 'lbank' and CONFIG['api_key'] and CONFIG['secret_key']:
            try:
                lbank = LBankAPI(CONFIG['api_key'], CONFIG['secret_key'])
                # LBank uses 'buy'/'sell'. If side is LONG -> buy, SHORT -> sell
                lbank_side = 'buy' if side == 'LONG' else 'sell'
                
                # ارسال سفارش لیمیت
                result = lbank.create_order(symbol, lbank_side, 'limit', entry_price, amount)
                
                if result.get('result') == 'true':
                    exchange_order_id = result.get('order_id', 'UNKNOWN')
                    logging.info(f"LBank Trade Success: {exchange_order_id}")
                else:
                    error_msg = result.get('error_code', 'Unknown Error')
                    logging.error(f"LBank Trade Failed: {error_msg}")
                    return {'success': False, 'error': f"Exchange Error: {error_msg}"}
            except Exception as e:
                logging.error(f"LBank Exception: {e}")
                return {'success': False, 'error': f"Exchange Exception: {str(e)}"}
        
        # محاسبه کمیسیون
        commission = amount * CONFIG['commission'] / 100
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''INSERT INTO trades 
                     (signal_id, symbol, side, entry_price, amount, leverage, 
                      stop_loss, take_profit, commission, exchange)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (signal['id'], symbol, side, entry_price, amount, leverage,
                   stop_loss, take_profit, commission, CONFIG['exchange']))
        
        trade_id = c.lastrowid
        conn.commit()
        conn.close()
        
        AutoTrader.daily_trades += 1
        AutoTrader.open_trades[trade_id] = {
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'amount': amount,
            'leverage': leverage
        }
        
        return {'success': True, 'trade_id': trade_id}
    
    @staticmethod
    def check_open_trades(market_data):
        """بررسی معاملات باز"""
        price_map = {item['symbol']: item['price'] for item in market_data}
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        for trade_id, trade in list(AutoTrader.open_trades.items()):
            symbol = trade['symbol']
            if symbol not in price_map:
                continue
            
            current_price = price_map[symbol]
            side = trade['side']
            entry_price = trade['entry_price']
            stop_loss = trade['stop_loss']
            take_profit = trade['take_profit']
            amount = trade['amount']
            leverage = trade['leverage']
            
            should_close = False
            close_reason = None
            
            if side == 'LONG':
                if current_price <= stop_loss:
                    should_close = True
                    close_reason = 'stop_loss'
                elif current_price >= take_profit:
                    should_close = True
                    close_reason = 'take_profit'
            else:  # SHORT
                if current_price >= stop_loss:
                    should_close = True
                    close_reason = 'stop_loss'
                elif current_price <= take_profit:
                    should_close = True
                    close_reason = 'take_profit'
            
            if should_close:
                # محاسبه PnL
                if side == 'LONG':
                    pnl = (current_price - entry_price) / entry_price * amount * leverage
                else:
                    pnl = (entry_price - current_price) / entry_price * amount * leverage
                
                pnl_percent = ((current_price - entry_price) / entry_price) * 100
                if side == 'SHORT':
                    pnl_percent = -pnl_percent
                
                commission = amount * CONFIG['commission'] / 100 * 2  # ورود + خروج
                net_pnl = pnl - commission
                
                c.execute('''UPDATE trades SET 
                             exit_price = ?, pnl = ?, pnl_percent = ?, 
                             commission = ?, net_pnl = ?, status = 'closed', closed_at = ?
                             WHERE id = ?''',
                          (current_price, pnl, pnl_percent, commission, net_pnl, 
                           datetime.now(), trade_id))
                
                # بروزرسانی آمار
                if net_pnl < 0:
                    AutoTrader.consecutive_losses += 1
                else:
                    AutoTrader.consecutive_losses = 0
                
                del AutoTrader.open_trades[trade_id]
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_stats():
        """آمار معاملات"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # روزانه
        today = datetime.now().date().isoformat()
        c.execute('''SELECT 
                     COUNT(*) as total,
                     SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                     SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losses,
                     SUM(net_pnl) as total_pnl,
                     SUM(commission) as total_commission
                     FROM trades WHERE DATE(opened_at) = ?''', (today,))
        daily = c.fetchone()
        
        # ماهانه
        month_start = datetime.now().replace(day=1).date().isoformat()
        c.execute('''SELECT 
                     COUNT(*) as total,
                     SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                     SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as losses,
                     SUM(net_pnl) as total_pnl,
                     SUM(commission) as total_commission
                     FROM trades WHERE DATE(opened_at) >= ?''', (month_start,))
        monthly = c.fetchone()
        
        conn.close()
        
        def calc_stats(row):
            if not row or not row[0]:
                return {'total': 0, 'wins': 0, 'losses': 0, 'pnl': 0, 'commission': 0, 'win_rate': 0}
            total = row[0] or 0
            wins = row[1] or 0
            return {
                'total': total,
                'wins': wins,
                'losses': row[2] or 0,
                'pnl': round(row[3] or 0, 2),
                'commission': round(row[4] or 0, 2),
                'win_rate': round(wins / total * 100, 1) if total > 0 else 0
            }
        
        return {
            'daily': calc_stats(daily),
            'monthly': calc_stats(monthly),
            'is_running': AutoTrader.is_running,
            'daily_trades': AutoTrader.daily_trades,
            'consecutive_losses': AutoTrader.consecutive_losses,
            'open_trades': len(AutoTrader.open_trades)
        }

# ═══════════════════════════════════════════════════════════════════════════
# Background Worker
# ═══════════════════════════════════════════════════════════════════════════

def background_worker():
    """کارگر پس‌زمینه برای بروزرسانی"""
    print("🔄 Background worker started")
    while True:
        try:
            # دریافت قیمت (با استفاده از api_source از CONFIG)
            market_data = MarketAPI.fetch(CONFIG['api_source'])
            
            if market_data:
                print(f"📊 Market data fetched: {len(market_data)} symbols")
                # تشخیص نهنگ و پامپ/دامپ
                WhaleDetector.detect(market_data)
                
                # بررسی سیگنال‌های در انتظار (اولویت اول - باید قبل از اتوترید باشد)
                SignalValidator.check_pending_signals(market_data)
                SignalValidator.check_pending_pumps(market_data)
                
                # اتوترید (بعد از اعتبارسنجی)
                if AutoTrader.is_running:
                    AutoTrader.check_open_trades(market_data)
                    
                    # ترید جدید - بررسی صف سیگنال‌های معتبر
                    can, _ = AutoTrader.can_trade()
                    if can:
                        queue = AutoTrader.get_trade_queue()
                        if queue:
                            # اجرای معامله برای اولین سیگنال معتبر در صف
                            result = AutoTrader.execute_trade(queue[0])
                            if result.get('success'):
                                print(f"✅ معامله اجرا شد: {queue[0]['symbol']} {queue[0]['signal_type']}")
                            else:
                                print(f"⚠️ خطا در معامله: {result.get('error', 'Unknown')}")
            
            time.sleep(CONFIG['update_interval'])
        
        except Exception as e:
            print(f"❌ Background Error: {e}")
            time.sleep(10)

# شروع کارگر پس‌زمینه
worker_thread = threading.Thread(target=background_worker, daemon=True)

# ═══════════════════════════════════════════════════════════════════════════
# Flask Routes
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    """داشبورد کنترلی"""
    # اطمینان از اینکه worker thread در حال اجرا است
    global worker_thread
    if not worker_thread.is_alive():
        print("⚠️ Worker thread died, restarting...")
        worker_thread = threading.Thread(target=background_worker, daemon=True)
        worker_thread.start()
    return render_template_string(DASHBOARD_HTML)

@app.route('/autotrade')
def autotrade_dashboard():
    """داشبورد اتوترید"""
    return render_template_string(AUTOTRADE_HTML)

@app.route('/api/market')
def api_market():
    """دریافت دیتای بازار - با هماهنگی انتخاب صرافی (بدون cache)"""
    source = request.args.get('source', CONFIG['api_source'])
    
    # اگر sync فعال است، از CONFIG استفاده کن
    if CONFIG.get('api_source_sync', True):
        source = CONFIG['api_source']
    
    # همیشه دیتای fresh بگیر (بدون cache)
    data = MarketAPI.fetch(source)
    
    # بررسی یکتایی symbol ها برای جلوگیری از تکرار
    if data:
        seen = set()
        unique_data = []
        for item in data:
            if item['symbol'] not in seen:
                seen.add(item['symbol'])
                unique_data.append(item)
        data = unique_data
    
    return jsonify({
        'success': data is not None, 
        'data': data or [], 
        'source': source,
        'count': len(data) if data else 0,
        'timestamp': datetime.now().isoformat()  # برای ردیابی freshness
    })

@app.route('/api/whales')
def api_whales():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM whales ORDER BY timestamp DESC LIMIT 100')
    columns = [desc[0] for desc in c.description]
    whales = [dict(zip(columns, row)) for row in c.fetchall()]
    
    # Whale Flow
    c.execute('''SELECT 
                 SUM(CASE WHEN whale_type = 'buy' THEN volume ELSE 0 END) as inflow,
                 SUM(CASE WHEN whale_type = 'sell' THEN volume ELSE 0 END) as outflow
                 FROM whales WHERE timestamp > datetime('now', '-24 hours')''')
    flow = c.fetchone()
    
    conn.close()
    
    return jsonify({
        'whales': whales,
        'flow': {
            'inflow': flow[0] or 0,
            'outflow': flow[1] or 0,
            'net': (flow[0] or 0) - (flow[1] or 0)
        }
    })

@app.route('/api/signals')
def api_signals():
    """دریافت سیگنال‌ها - همیشه fresh"""
    status = request.args.get('status', 'all')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if status == 'all':
        c.execute('SELECT * FROM signals ORDER BY timestamp DESC LIMIT 100')
    else:
        c.execute('SELECT * FROM signals WHERE final_status = ? ORDER BY timestamp DESC LIMIT 100', (status,))
    
    columns = [desc[0] for desc in c.description]
    signals = [dict(zip(columns, row)) for row in c.fetchall()]
    
    # آمار
    c.execute('''SELECT 
                 SUM(CASE WHEN final_status = 'valid' THEN 1 ELSE 0 END) as valid,
                 SUM(CASE WHEN final_status = 'invalid' THEN 1 ELSE 0 END) as invalid,
                 SUM(CASE WHEN final_status = 'pending' THEN 1 ELSE 0 END) as pending
                 FROM signals''')
    stats = c.fetchone()
    
    conn.close()
    
    valid = stats[0] or 0
    invalid = stats[1] or 0
    total = valid + invalid
    
    return jsonify({
        'signals': signals,
        'stats': {
            'valid': valid,
            'invalid': invalid,
            'pending': stats[2] or 0,
            'accuracy': round(valid / total * 100, 1) if total > 0 else 0
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/pump_dumps')
def api_pump_dumps():
    """دریافت پامپ/دامپ‌ها - همیشه fresh"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM pump_dumps ORDER BY timestamp DESC LIMIT 100')
    columns = [desc[0] for desc in c.description]
    data = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return jsonify({
        'data': data,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/indicators/<symbol>')
def api_indicators(symbol):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM indicators WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1', (symbol,))
    row = c.fetchone()
    conn.close()
    
    if row:
        columns = [desc[0] for desc in c.description]
        return jsonify(dict(zip(columns, row)))
    return jsonify({})

@app.route('/api/trades')
def api_trades():
    status = request.args.get('status', 'all')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if status == 'all':
        c.execute('SELECT * FROM trades ORDER BY opened_at DESC LIMIT 100')
    else:
        c.execute('SELECT * FROM trades WHERE status = ? ORDER BY opened_at DESC LIMIT 100', (status,))
    
    columns = [desc[0] for desc in c.description]
    trades = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    
    return jsonify(trades)

@app.route('/api/trade_queue')
def api_trade_queue():
    return jsonify(AutoTrader.get_trade_queue())

@app.route('/api/trade_stats')
def api_trade_stats():
    return jsonify(AutoTrader.get_stats())

@app.route('/api/account')
def api_account():
    return jsonify(AutoTrader.get_account_info())

@app.route('/api/validation_data')
def api_validation_data():
    """دریافت داده‌های اعتبارسنجی (سیگنال، نهنگ، پامپ) - همیشه fresh"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # دریافت سیگنال‌های معتبر و در انتظار (تازه‌ترین‌ها)
    c.execute('SELECT * FROM signals ORDER BY timestamp DESC LIMIT 100')
    sig_cols = [desc[0] for desc in c.description]
    signals = [dict(zip(sig_cols, row)) for row in c.fetchall()]
    
    # دریافت نهنگ‌ها (تازه‌ترین‌ها)
    c.execute('SELECT * FROM whales ORDER BY timestamp DESC LIMIT 100')
    whale_cols = [desc[0] for desc in c.description]
    whales = [dict(zip(whale_cols, row)) for row in c.fetchall()]
    
    # دریافت پامپ/دامپ‌ها (تازه‌ترین‌ها)
    c.execute('SELECT * FROM pump_dumps ORDER BY timestamp DESC LIMIT 100')
    pump_cols = [desc[0] for desc in c.description]
    pump_dumps = [dict(zip(pump_cols, row)) for row in c.fetchall()]
    
    conn.close()
    
    # ترکیب داده‌ها برای دیتاگرید
    grid_data = []
    
    for s in signals:
        grid_data.append({
            'type': 'signal',
            'symbol': s['symbol'],
            'action': s['signal_type'], # LONG/SHORT
            'price': s['entry_price'],
            'score': s['score'],
            'status': s['final_status'],
            'source': s['source'],
            'time': s['timestamp'],
            'details': f"مرحله: {s.get('valid_4min') or s.get('valid_2min') or s.get('valid_1min') or 0}/3"
        })

    for w in whales:
        grid_data.append({
            'type': 'whale',
            'symbol': w['symbol'],
            'action': 'BUY' if w['whale_type'] == 'buy' else 'SELL',
            'price': w['price'],
            'score': w['confidence_score'],
            'status': 'detected',
            'source': 'Whale Monitor',
            'time': w['timestamp'],
            'details': f"حجم: {w['volume']:,.0f}$"
        })
        
    for p in pump_dumps:
        grid_data.append({
            'type': 'pump_dump',
            'symbol': p['symbol'],
            'action': p['event_type'].upper(),
            'price': p['price_after'],
            'score': p['score'],
            'status': 'valid' if p['is_valid'] else 'invalid',
            'source': 'Pump Detector',
            'time': p['timestamp'],
            'details': f"تغییر: {p['change_percent']:.2f}%"
        })

    return jsonify(grid_data)

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """دریافت و بروزرسانی تنظیمات"""
    global CONFIG
    try:
        if request.method == 'GET':
            # برگرداندن تنظیمات فعلی
            return jsonify({'success': True, 'config': CONFIG})
        
        # POST: بروزرسانی تنظیمات
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        # بروزرسانی مقادیر مجاز
        allowed_keys = [
            'min_score_for_trade', 'trade_amount', 'stop_loss', 'take_profit',
            'api_source', 'validation_times', 'validation_weights',
            'pump_dump_time', 'pump_dump_weight', 'whale_threshold'
        ]
        
        updated = False
        for key in allowed_keys:
            if key in data:
                # تبدیل نوع داده در صورت نیاز
                if key in ['min_score_for_trade']:
                    CONFIG[key] = int(data[key])
                elif key in ['validation_times', 'validation_weights']:
                    CONFIG[key] = data[key]  # لیست
                elif key == 'api_source':
                    # هماهنگ کردن انتخاب صرافی
                    if CONFIG.get('api_source_sync', True):
                        CONFIG[key] = data[key]
                        print(f"🔄 API Source synced: {data[key]}")
                else:
                    CONFIG[key] = float(data[key])
                updated = True
        
        if updated:
            print(f"✅ Config Updated: {[k for k in allowed_keys if k in data]}")
            return jsonify({'success': True, 'config': CONFIG})
        else:
            return jsonify({'success': False, 'error': 'No valid keys provided'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

        


@app.route('/api/autotrade/start', methods=['POST'])
def api_autotrade_start():
    AutoTrader.is_running = True
    return jsonify({'success': True, 'message': 'اتوترید شروع شد'})

@app.route('/api/autotrade/stop', methods=['POST'])
def api_autotrade_stop():
    AutoTrader.is_running = False
    return jsonify({'success': True, 'message': 'اتوترید متوقف شد'})

@app.route('/api/export/<table>')
def api_export(table):
    import csv
    from io import StringIO
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f'SELECT * FROM {table}')
    columns = [desc[0] for desc in c.description]
    rows = c.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(rows)
    
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': f'attachment; filename={table}.csv'
    }

# ═══════════════════════════════════════════════════════════════════════════
# HTML Templates
# ═══════════════════════════════════════════════════════════════════════════

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🐋 Whale Hunter Pro v6.0 - داشبورد کنترلی</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * { font-family: 'Vazirmatn', sans-serif; }
        .glass { background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(10px); }
        .live { animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    </style>
</head>
<body class="bg-gradient-to-br from-slate-950 via-blue-950 to-slate-950 text-white min-h-screen">
    
    <!-- Header -->
    <header class="glass border-b border-slate-700 sticky top-0 z-50">
        <div class="container mx-auto px-4 py-3">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-4">
                    <h1 class="text-2xl font-bold">🐋 Whale Hunter Pro v6.0</h1>
                    <span class="px-3 py-1 rounded-full bg-green-500/20 text-green-400 text-sm live">● آنلاین</span>
                </div>
                <div class="flex items-center gap-4">
                    <select id="apiSource" onchange="changeAPI()" class="bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        <option value="coingecko">🦎 CoinGecko</option>
                        <option value="kucoin">🟢 KuCoin</option>
                        <option value="bybit">🟡 Bybit</option>
                    </select>
                    <a href="/autotrade" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg">🤖 اتوترید</a>
                </div>
            </div>
        </div>
    </header>
    
    <main class="container mx-auto px-4 py-6">
        
        <!-- Stats Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="text-slate-400 text-sm">نهنگ مادر</div>
                <div class="text-2xl font-bold text-blue-400" id="statWhales">0</div>
            </div>
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="text-slate-400 text-sm">سیگنال معتبر</div>
                <div class="text-2xl font-bold text-green-400" id="statValid">0</div>
            </div>
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="text-slate-400 text-sm">در انتظار</div>
                <div class="text-2xl font-bold text-yellow-400" id="statPending">0</div>
            </div>
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="text-slate-400 text-sm">دقت سیگنال</div>
                <div class="text-2xl font-bold text-purple-400" id="statAccuracy">0%</div>
            </div>
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="text-slate-400 text-sm">پامپ/دامپ</div>
                <div class="text-2xl font-bold text-orange-400" id="statPumpDump">0</div>
            </div>
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="text-slate-400 text-sm">Whale Flow</div>
                <div class="text-2xl font-bold text-cyan-400" id="statFlow">$0</div>
            </div>
        </div>
        
        <!-- Formula Box -->
        <div class="glass rounded-xl p-4 border border-purple-500/30 mb-6">
            <h3 class="font-bold text-purple-400 mb-3">🧮 فرمول اعتبارسنجی (پارامتریک)</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="bg-slate-800 rounded-lg p-3">
                    <div class="text-sm text-slate-400 mb-2">زمان‌های اعتبارسنجی</div>
                    <div class="flex gap-2">
                        <input type="number" id="time1" value="1" class="w-16 bg-slate-700 rounded px-2 py-1 text-center">
                        <input type="number" id="time2" value="2" class="w-16 bg-slate-700 rounded px-2 py-1 text-center">
                        <input type="number" id="time3" value="4" class="w-16 bg-slate-700 rounded px-2 py-1 text-center">
                        <span class="text-slate-400">دقیقه</span>
                    </div>
                </div>
                <div class="bg-slate-800 rounded-lg p-3">
                    <div class="text-sm text-slate-400 mb-2">وزن‌ها</div>
                    <div class="flex gap-2">
                        <input type="number" id="weight1" value="20" class="w-16 bg-slate-700 rounded px-2 py-1 text-center">
                        <input type="number" id="weight2" value="30" class="w-16 bg-slate-700 rounded px-2 py-1 text-center">
                        <input type="number" id="weight3" value="50" class="w-16 bg-slate-700 rounded px-2 py-1 text-center">
                        <span class="text-slate-400">%</span>
                    </div>
                </div>
                <div class="bg-slate-800 rounded-lg p-3">
                    <div class="text-sm text-slate-400 mb-2">پامپ/دامپ</div>
                    <div class="flex gap-2 items-center">
                        <input type="number" id="pumpTime" value="1" class="w-16 bg-slate-700 rounded px-2 py-1 text-center">
                        <span class="text-slate-400">دقیقه</span>
                        <input type="number" id="pumpWeight" value="80" class="w-16 bg-slate-700 rounded px-2 py-1 text-center">
                        <span class="text-slate-400">وزن</span>
                    </div>
                </div>
            </div>
            <button onclick="saveConfig()" class="mt-3 bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg">💾 ذخیره تنظیمات</button>
        </div>
        
        <!-- Tabs -->
        <div class="flex gap-2 mb-4 border-b border-slate-700 pb-2">
            <button onclick="showTab('market')" class="tab-btn px-4 py-2 rounded-lg bg-slate-700" data-tab="market">📊 بازار</button>
            <button onclick="showTab('whales')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700" data-tab="whales">🐋 نهنگ‌ها</button>
            <button onclick="showTab('signals')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700" data-tab="signals">📡 سیگنال‌ها</button>
            <button onclick="showTab('pumps')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700" data-tab="pumps">🚀 پامپ/دامپ</button>
            <button onclick="showTab('indicators')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700" data-tab="indicators">📈 اندیکاتورها</button>
        </div>
        
        <!-- Market Tab -->
        <div id="market-tab" class="tab-content">
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="font-bold">📊 بازار (هر 10 ثانیه)</h3>
                    <div class="flex gap-2">
                        <input type="text" id="searchMarket" placeholder="🔍 جستجو..." 
                               class="bg-slate-800 rounded-lg px-3 py-1 border border-slate-600" onkeyup="filterMarket()">
                        <select id="filterMarket" class="bg-slate-800 rounded-lg px-3 py-1 border border-slate-600" onchange="filterMarket()">
                            <option value="all">همه</option>
                            <option value="pump">🟢 پامپ (+5%)</option>
                            <option value="dump">🔴 دامپ (-5%)</option>
                            <option value="whale">🐋 نهنگ</option>
                        </select>
                    </div>
                </div>
                <div class="overflow-x-auto max-h-96">
                    <table class="w-full text-sm">
                        <thead class="bg-slate-800 sticky top-0">
                            <tr class="text-slate-400">
                                <th class="text-right py-2 px-2 cursor-pointer" onclick="sortMarket('symbol')">نماد</th>
                                <th class="text-right py-2 px-2 cursor-pointer" onclick="sortMarket('price')">قیمت</th>
                                <th class="text-right py-2 px-2 cursor-pointer" onclick="sortMarket('change_24h')">تغییر 24h</th>
                                <th class="text-right py-2 px-2 cursor-pointer" onclick="sortMarket('volume')">حجم</th>
                                <th class="text-right py-2 px-2">RSI</th>
                                <th class="text-right py-2 px-2">MACD</th>
                                <th class="text-right py-2 px-2">وضعیت</th>
                                <th class="text-right py-2 px-2">عملیات</th>
                            </tr>
                        </thead>
                        <tbody id="marketTable"></tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Whales Tab -->
        <div id="whales-tab" class="tab-content hidden">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="lg:col-span-2 glass rounded-xl p-4 border border-slate-700">
                    <h3 class="font-bold mb-3">🐋 نهنگ‌های اخیر</h3>
                    <div id="whalesList" class="space-y-2 max-h-96 overflow-y-auto"></div>
                </div>
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <h3 class="font-bold mb-3">💧 Whale Flow</h3>
                    <div class="space-y-4">
                        <div>
                            <div class="flex justify-between text-sm mb-1">
                                <span>ورود</span>
                                <span class="text-green-400" id="flowIn">$0</span>
                            </div>
                            <div class="w-full bg-slate-700 rounded-full h-3">
                                <div id="flowInBar" class="bg-green-500 h-3 rounded-full" style="width: 50%"></div>
                            </div>
                        </div>
                        <div>
                            <div class="flex justify-between text-sm mb-1">
                                <span>خروج</span>
                                <span class="text-red-400" id="flowOut">$0</span>
                            </div>
                            <div class="w-full bg-slate-700 rounded-full h-3">
                                <div id="flowOutBar" class="bg-red-500 h-3 rounded-full" style="width: 50%"></div>
                            </div>
                        </div>
                        <div class="pt-3 border-t border-slate-600">
                            <div class="flex justify-between">
                                <span>خالص</span>
                                <span id="flowNet" class="font-bold text-xl">$0</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Signals Tab -->
        <div id="signals-tab" class="tab-content hidden">
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="font-bold">📡 سیگنال‌ها (اعتبارسنجی 1، 2، 4 دقیقه)</h3>
                    <div class="flex gap-2">
                        <button onclick="filterSignals('all')" class="px-3 py-1 rounded bg-slate-700">همه</button>
                        <button onclick="filterSignals('valid')" class="px-3 py-1 rounded bg-green-500/20 text-green-400">✅ معتبر</button>
                        <button onclick="filterSignals('invalid')" class="px-3 py-1 rounded bg-red-500/20 text-red-400">❌ نامعتبر</button>
                        <button onclick="filterSignals('pending')" class="px-3 py-1 rounded bg-yellow-500/20 text-yellow-400">⏳ انتظار</button>
                        <a href="/api/export/signals" class="px-3 py-1 rounded bg-blue-600">📥 CSV</a>
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                        <thead class="bg-slate-800">
                            <tr class="text-slate-400">
                                <th class="text-right py-2 px-2">زمان</th>
                                <th class="text-right py-2 px-2">نماد</th>
                                <th class="text-right py-2 px-2">نوع</th>
                                <th class="text-right py-2 px-2">قیمت ورود</th>
                                <th class="text-right py-2 px-2">1 دقیقه</th>
                                <th class="text-right py-2 px-2">2 دقیقه</th>
                                <th class="text-right py-2 px-2">4 دقیقه</th>
                                <th class="text-right py-2 px-2">RSI</th>
                                <th class="text-right py-2 px-2">MACD</th>
                                <th class="text-right py-2 px-2">امتیاز</th>
                                <th class="text-right py-2 px-2">وضعیت</th>
                            </tr>
                        </thead>
                        <tbody id="signalsTable"></tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Pumps Tab -->
        <div id="pumps-tab" class="tab-content hidden">
            <div class="glass rounded-xl p-4 border border-slate-700">
                <h3 class="font-bold mb-4">🚀 پامپ/دامپ (اعتبارسنجی <span id="pumpTimeDisplay">1</span> دقیقه)</h3>
                <div id="pumpsList" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3"></div>
            </div>
        </div>
        
        <!-- Indicators Tab -->
        <div id="indicators-tab" class="tab-content hidden">
            <div class="glass rounded-xl p-4 border border-slate-700">
                <h3 class="font-bold mb-4">📈 اندیکاتورها (ذخیره در دیتابیس)</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div class="bg-slate-800 rounded-lg p-4">
                        <h4 class="font-bold text-purple-400 mb-2">RSI</h4>
                        <div class="flex gap-2 items-center">
                            <span class="text-slate-400">دوره:</span>
                            <input type="number" id="rsiPeriod" value="14" class="w-16 bg-slate-700 rounded px-2 py-1">
                        </div>
                        <div class="flex gap-4 mt-2 text-sm">
                            <span>Oversold: <input type="number" id="rsiOversold" value="30" class="w-12 bg-slate-700 rounded px-1"></span>
                            <span>Overbought: <input type="number" id="rsiOverbought" value="70" class="w-12 bg-slate-700 rounded px-1"></span>
                        </div>
                    </div>
                    <div class="bg-slate-800 rounded-lg p-4">
                        <h4 class="font-bold text-cyan-400 mb-2">MACD</h4>
                        <div class="flex gap-2 items-center text-sm">
                            <span>Fast: <input type="number" id="macdFast" value="12" class="w-12 bg-slate-700 rounded px-1"></span>
                            <span>Slow: <input type="number" id="macdSlow" value="26" class="w-12 bg-slate-700 rounded px-1"></span>
                            <span>Signal: <input type="number" id="macdSignal" value="9" class="w-12 bg-slate-700 rounded px-1"></span>
                        </div>
                    </div>
                    <div class="bg-slate-800 rounded-lg p-4">
                        <h4 class="font-bold text-orange-400 mb-2">Volume</h4>
                        <div class="text-sm text-slate-400">حجم معاملات و میانگین ذخیره می‌شود</div>
                    </div>
                </div>
            </div>
        </div>
        
    </main>
    
    <script>
        let marketData = [];
        let signalFilter = 'all';
        let sortColumn = 'volume';
        let sortDirection = 'desc';
        
        // Fallback API Functions (در صورت قطع بک‌اند)
        let backendOnline = true;
        let fallbackRetryCount = 0;
        const MAX_FALLBACK_RETRIES = 3;
        
        async function fetchWithFallback(url, fallbackFn) {
            try {
                // اضافه کردن no-cache headers برای fresh data
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 8000); // 8 second timeout
                
                const response = await fetch(url, {
                    cache: 'no-store',
                    signal: controller.signal,
                    headers: {
                        'Cache-Control': 'no-cache, no-store, must-revalidate',
                        'Pragma': 'no-cache',
                        'Expires': '0'
                    }
                });
                
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const data = await response.json();
                backendOnline = true;
                fallbackRetryCount = 0;
                return data;
            } catch (e) {
                if (e.name === 'AbortError') {
                    console.warn('⏱️ Request timeout:', url);
                } else {
                    console.warn('⚠️ Backend error:', e.message);
                }
                
                backendOnline = false;
                fallbackRetryCount++;
                
                if (fallbackRetryCount <= MAX_FALLBACK_RETRIES && fallbackFn) {
                    console.log(`🔄 Trying fallback (${fallbackRetryCount}/${MAX_FALLBACK_RETRIES})...`);
                    try {
                        return await fallbackFn();
                    } catch (fallbackError) {
                        console.error('❌ Fallback also failed:', fallbackError);
                    }
                }
                
                // Return empty data structure instead of throwing
                if (url.includes('/api/market')) {
                    return {success: false, data: []};
                } else if (url.includes('/api/whales')) {
                    return {whales: [], flow: {inflow: 0, outflow: 0, net: 0}};
                } else if (url.includes('/api/signals')) {
                    return {signals: [], stats: {valid: 0, invalid: 0, pending: 0, accuracy: 0}};
                } else if (url.includes('/api/pump_dumps')) {
                    return {data: []};
                }
                
                return {};
            }
        }
        
        // Fallback: مستقیم از CoinGecko
        async function fetchMarketFallback() {
            try {
                const res = await fetch('https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page=100&page=1');
                const data = await res.json();
                return {
                    success: true,
                    data: data.map(coin => ({
                        symbol: coin.symbol.toUpperCase() + 'USDT',
                        price: coin.current_price,
                        change_24h: coin.price_change_percentage_24h || 0,
                        volume: coin.total_volume || 0
                    })),
                    source: 'coingecko_fallback'
                };
            } catch (e) {
                console.error('Fallback failed:', e);
                return {success: false, data: []};
            }
        }
        
        // Fetch Data (بهینه‌سازی شده - همه درخواست‌ها به صورت موازی)
        async function fetchData() {
            const startTime = performance.now();
            try {
                // اضافه کردن timestamp برای جلوگیری از cache مرورگر
                const timestamp = new Date().getTime();
                const apiSource = document.getElementById('apiSource')?.value || 'coingecko';
                
                // اجرای موازی همه درخواست‌ها برای سرعت بیشتر (با timestamp برای fresh data)
                const [marketRes, whalesRes, signalsRes, pumpsRes] = await Promise.all([
                    fetchWithFallback(`/api/market?source=${apiSource}&_t=${timestamp}`, fetchMarketFallback),
                    fetchWithFallback(`/api/whales?_t=${timestamp}`, () => ({whales: [], flow: {inflow: 0, outflow: 0, net: 0}})),
                    fetchWithFallback(`/api/signals?status=${signalFilter}&_t=${timestamp}`, () => ({signals: [], stats: {valid: 0, invalid: 0, pending: 0, accuracy: 0}})),
                    fetchWithFallback(`/api/pump_dumps?_t=${timestamp}`, () => ({data: []}))
                ]);
                
                // پردازش نتایج
                if (marketRes && marketRes.success && marketRes.data) {
                    marketData = marketRes.data;
                    renderMarket();
                } else if (marketRes && marketRes.data) {
                    // اگر success field نبود ولی data بود
                    marketData = marketRes.data;
                    renderMarket();
                }
                
                // پردازش whales
                if (whalesRes) {
                    renderWhales(whalesRes);
                }
                
                // پردازش signals
                if (signalsRes) {
                    renderSignals(signalsRes);
                }
                
                // پردازش pumps (ممکن است data یا array باشد)
                const pumps = pumpsRes?.data || (Array.isArray(pumpsRes) ? pumpsRes : []);
                renderPumps(pumps);
                
                // Update stats (با null check)
                try {
                    if (whalesRes) {
                        const statWhales = document.getElementById('statWhales');
                        const statFlow = document.getElementById('statFlow');
                        if (statWhales) statWhales.textContent = (whalesRes.whales || []).length;
                        if (statFlow) statFlow.textContent = '$' + formatNumber((whalesRes.flow || {}).net || 0);
                    }
                    if (signalsRes) {
                        const statValid = document.getElementById('statValid');
                        const statPending = document.getElementById('statPending');
                        const statAccuracy = document.getElementById('statAccuracy');
                        if (statValid) statValid.textContent = (signalsRes.stats || {}).valid || 0;
                        if (statPending) statPending.textContent = (signalsRes.stats || {}).pending || 0;
                        if (statAccuracy) statAccuracy.textContent = ((signalsRes.stats || {}).accuracy || 0) + '%';
                    }
                    const statPumpDump = document.getElementById('statPumpDump');
                    if (statPumpDump) statPumpDump.textContent = pumps.length;
                } catch (statError) {
                    console.warn('⚠️ Error updating stats:', statError);
                }
                
                // نمایش زمان اجرا (برای دیباگ)
                const elapsed = (performance.now() - startTime).toFixed(0);
                if (elapsed > 1000) {
                    console.warn(`⚠️ Fetch took ${elapsed}ms (target: <1000ms)`);
                }
                
                // Update connection status
                const statusEl = document.querySelector('.live');
                if (statusEl) {
                    statusEl.textContent = backendOnline ? '● آنلاین' : '⚠️ Fallback Mode';
                    statusEl.className = backendOnline ? 'px-3 py-1 rounded-full bg-green-500/20 text-green-400 text-sm live' : 'px-3 py-1 rounded-full bg-yellow-500/20 text-yellow-400 text-sm live';
                }
                
            } catch (e) {
                console.error('❌ Fetch error:', e);
                console.error('Error stack:', e.stack);
                
                // نمایش خطا در UI
                const statusEl = document.querySelector('.live');
                if (statusEl) {
                    statusEl.textContent = '❌ خطا در دریافت دیتا';
                    statusEl.className = 'px-3 py-1 rounded-full bg-red-500/20 text-red-400 text-sm';
                }
                
                // Retry after 5 seconds
                setTimeout(() => {
                    console.log('🔄 Retrying fetch after error...');
                    fetchData();
                }, 5000);
            }
        }
        
        function renderMarket() {
            if (!marketData || marketData.length === 0) {
                document.getElementById('marketTable').innerHTML = '<tr><td colspan="8" class="text-center text-slate-400 p-4">در حال بارگذاری دیتا...</td></tr>';
                return;
            }
            
            // ایجاد یک Map برای حذف تکرارها (اگر ارزی در HTML هست ولی در بک‌اند نیست)
            const symbolMap = new Map();
            marketData.forEach(item => {
                const symbol = item.symbol;
                // اگر قبلاً وجود نداشت یا این یکی جدیدتر/بهتر است، اضافه کن
                if (!symbolMap.has(symbol) || (item.volume || 0) > (symbolMap.get(symbol).volume || 0)) {
                    symbolMap.set(symbol, item);
                }
            });
            
            // تبدیل Map به Array
            let uniqueData = Array.from(symbolMap.values());
            
            const search = document.getElementById('searchMarket').value.toLowerCase();
            const filter = document.getElementById('filterMarket').value;
            
            let data = uniqueData.filter(item => {
                if (search && !item.symbol.toLowerCase().includes(search)) return false;
                if (filter === 'pump' && item.change_24h <= 5) return false;
                if (filter === 'dump' && item.change_24h >= -5) return false;
                if (filter === 'whale' && item.volume < 500000) return false;
                return true;
            });
            
            data.sort((a, b) => {
                if (sortDirection === 'asc') return a[sortColumn] - b[sortColumn];
                return b[sortColumn] - a[sortColumn];
            });
            
            document.getElementById('marketTable').innerHTML = data.slice(0, 100).map(item => `
                <tr class="border-b border-slate-700 hover:bg-slate-800">
                    <td class="py-2 px-2 font-bold">${item.symbol.replace('USDT', '')}</td>
                    <td class="py-2 px-2">$${formatPrice(item.price)}</td>
                    <td class="py-2 px-2 ${item.change_24h >= 0 ? 'text-green-400' : 'text-red-400'}">
                        ${item.change_24h >= 0 ? '+' : ''}${item.change_24h.toFixed(2)}%
                    </td>
                    <td class="py-2 px-2">$${formatNumber(item.volume)}</td>
                    <td class="py-2 px-2">-</td>
                    <td class="py-2 px-2">-</td>
                    <td class="py-2 px-2">
                        ${item.change_24h > 5 ? '<span class="text-green-400">پامپ 🚀</span>' : 
                          item.change_24h < -5 ? '<span class="text-red-400">دامپ 💥</span>' : 
                          item.volume > 500000 ? '<span class="text-blue-400">نهنگ 🐋</span>' : '-'}
                    </td>
                    <td class="py-2 px-2">
                        <button onclick="trackSymbol('${item.symbol}')" class="bg-blue-600 hover:bg-blue-700 px-2 py-1 rounded text-xs">رصد</button>
                    </td>
                </tr>
            `).join('');
        }
        
        function renderWhales(data) {
            if (!data || !data.whales) {
                console.warn('No whales data:', data);
                document.getElementById('whalesList').innerHTML = '<div class="text-slate-400 text-center p-4">دیتا موجود نیست</div>';
                return;
            }
            const whales = data.whales.slice(0, 20);
            if (whales.length === 0) {
                document.getElementById('whalesList').innerHTML = '<div class="text-slate-400 text-center p-4">هنوز نهنگی شناسایی نشده</div>';
                return;
            }
            document.getElementById('whalesList').innerHTML = whales.map(w => `
                <div class="p-3 rounded-lg border ${w.whale_type === 'buy' ? 'border-green-500/30 bg-green-500/10' : 'border-red-500/30 bg-red-500/10'}">
                    <div class="flex justify-between items-center">
                        <div>
                            <span class="font-bold">${w.symbol.replace('USDT', '')}</span>
                            <span class="text-sm text-slate-400 mr-2">${w.whale_type === 'buy' ? '📥 خرید' : '📤 فروش'}</span>
                            ${w.pattern === 'bait_pecking' ? '<span class="text-yellow-400 text-sm">🎣 نوک‌زدن</span>' : ''}
                        </div>
                        <div class="text-left">
                            <div class="font-bold ${w.whale_type === 'buy' ? 'text-green-400' : 'text-red-400'}">$${formatNumber(w.volume)}</div>
                            <div class="text-xs text-slate-400">${new Date(w.timestamp).toLocaleTimeString('fa-IR')}</div>
                        </div>
                    </div>
                </div>
            `).join('');
            
            // Flow
            const flow = data.flow;
            const total = flow.inflow + flow.outflow || 1;
            document.getElementById('flowIn').textContent = '$' + formatNumber(flow.inflow);
            document.getElementById('flowOut').textContent = '$' + formatNumber(flow.outflow);
            document.getElementById('flowInBar').style.width = (flow.inflow / total * 100) + '%';
            document.getElementById('flowOutBar').style.width = (flow.outflow / total * 100) + '%';
            document.getElementById('flowNet').textContent = '$' + formatNumber(flow.net);
            document.getElementById('flowNet').className = 'font-bold text-xl ' + (flow.net >= 0 ? 'text-green-400' : 'text-red-400');
        }
        
        function renderSignals(data) {
            if (!data || !data.signals) {
                console.warn('No signals data:', data);
                document.getElementById('signalsTable').innerHTML = '<tr><td colspan="8" class="text-center text-slate-400 p-4">دیتا موجود نیست</td></tr>';
                return;
            }
            if (data.signals.length === 0) {
                document.getElementById('signalsTable').innerHTML = '<tr><td colspan="8" class="text-center text-slate-400 p-4">هنوز سیگنالی شناسایی نشده</td></tr>';
                return;
            }
            document.getElementById('signalsTable').innerHTML = data.signals.map(s => `
                <tr class="border-b border-slate-700 ${s.final_status === 'valid' ? 'bg-green-500/5' : s.final_status === 'invalid' ? 'bg-red-500/5' : ''}">
                    <td class="py-2 px-2 text-xs">${new Date(s.timestamp).toLocaleString('fa-IR')}</td>
                    <td class="py-2 px-2 font-bold">${s.symbol.replace('USDT', '')}</td>
                    <td class="py-2 px-2">
                        <span class="px-2 py-0.5 rounded text-xs ${s.signal_type === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">
                            ${s.signal_type}
                        </span>
                    </td>
                    <td class="py-2 px-2">$${formatPrice(s.entry_price)}</td>
                    <td class="py-2 px-2 ${s.valid_1min ? 'text-green-400' : s.price_1min ? 'text-red-400' : 'text-slate-400'}">
                        ${s.price_1min ? '$' + formatPrice(s.price_1min) : '⏳'}
                    </td>
                    <td class="py-2 px-2 ${s.valid_2min ? 'text-green-400' : s.price_2min ? 'text-red-400' : 'text-slate-400'}">
                        ${s.price_2min ? '$' + formatPrice(s.price_2min) : '⏳'}
                    </td>
                    <td class="py-2 px-2 ${s.valid_4min ? 'text-green-400' : s.price_4min ? 'text-red-400' : 'text-slate-400'}">
                        ${s.price_4min ? '$' + formatPrice(s.price_4min) : '⏳'}
                    </td>
                    <td class="py-2 px-2">${s.rsi ? s.rsi.toFixed(1) : '-'}</td>
                    <td class="py-2 px-2">${s.macd ? s.macd.toFixed(4) : '-'}</td>
                    <td class="py-2 px-2 font-bold">${s.score || 0}</td>
                    <td class="py-2 px-2">
                        ${s.final_status === 'valid' ? '✅' : s.final_status === 'invalid' ? '❌' : '⏳'}
                    </td>
                </tr>
            `).join('');
        }
        
        function renderPumps(data) {
            if (!data || !Array.isArray(data)) {
                console.warn('No pumps data:', data);
                document.getElementById('pumpsList').innerHTML = '<div class="text-slate-400 text-center p-4">دیتا موجود نیست</div>';
                return;
            }
            if (data.length === 0) {
                document.getElementById('pumpsList').innerHTML = '<div class="text-slate-400 text-center p-4">هنوز پامپ/دامپی شناسایی نشده</div>';
                return;
            }
            document.getElementById('pumpsList').innerHTML = data.slice(0, 24).map(p => `
                <div class="p-3 rounded-lg border ${p.event_type === 'pump' ? 'border-green-500/30 bg-green-500/10' : 'border-red-500/30 bg-red-500/10'}">
                    <div class="flex items-center justify-between">
                        <span class="font-bold">${p.symbol.replace('USDT', '')}</span>
                        <span class="text-lg">${p.event_type === 'pump' ? '🚀' : '💥'}</span>
                    </div>
                    <div class="text-xl font-bold ${p.event_type === 'pump' ? 'text-green-400' : 'text-red-400'}">
                        ${p.change_percent >= 0 ? '+' : ''}${p.change_percent.toFixed(2)}%
                    </div>
                    <div class="text-xs text-slate-400 mt-1">
                        ${p.is_valid ? '✅ معتبر' : '⏳ انتظار'} | امتیاز: ${p.score || 0}
                    </div>
                </div>
            `).join('');
        }
        
        function showTab(tab) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.getElementById(tab + '-tab').classList.remove('hidden');
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('bg-slate-700');
                if (btn.dataset.tab === tab) btn.classList.add('bg-slate-700');
            });
        }
        
        function filterSignals(status) {
            signalFilter = status;
            fetchData();
        }
        
        function filterMarket() {
            renderMarket();
        }
        
        function sortMarket(column) {
            if (sortColumn === column) {
                sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                sortColumn = column;
                sortDirection = 'desc';
            }
            renderMarket();
        }
        
        function trackSymbol(symbol) {
            alert('رصد ' + symbol + ' شروع شد!');
        }
        
        async function changeAPI() {
            const source = document.getElementById('apiSource').value;
            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({api_source: source})
                });
                const data = await res.json();
                if (data.success) {
                    console.log('✅ API Source synced:', source);
                    // آپدیت فوری دیتا
                    await fetchData();
                }
            } catch (e) {
                console.error('Error changing API:', e);
            }
        }
        
        // بارگذاری تنظیمات فعلی هنگام لود صفحه
        async function loadConfig() {
            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                if (data.success && data.config) {
                    // تنظیم select با مقدار فعلی
                    const apiSourceSelect = document.getElementById('apiSource');
                    if (apiSourceSelect && data.config.api_source) {
                        apiSourceSelect.value = data.config.api_source;
                    }
                }
            } catch (e) {
                console.error('Error loading config:', e);
            }
        }
        
        async function saveConfig() {
            const config = {
                validation_times: [
                    parseInt(document.getElementById('time1').value),
                    parseInt(document.getElementById('time2').value),
                    parseInt(document.getElementById('time3').value)
                ],
                validation_weights: [
                    parseInt(document.getElementById('weight1').value),
                    parseInt(document.getElementById('weight2').value),
                    parseInt(document.getElementById('weight3').value)
                ],
                pump_dump_time: parseInt(document.getElementById('pumpTime').value),
                pump_dump_weight: parseInt(document.getElementById('pumpWeight').value),
                rsi_period: parseInt(document.getElementById('rsiPeriod').value),
                rsi_oversold: parseInt(document.getElementById('rsiOversold').value),
                rsi_overbought: parseInt(document.getElementById('rsiOverbought').value),
                macd_fast: parseInt(document.getElementById('macdFast').value),
                macd_slow: parseInt(document.getElementById('macdSlow').value),
                macd_signal: parseInt(document.getElementById('macdSignal').value)
            };
            
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            });
            
            alert('✅ تنظیمات ذخیره شد');
        }
        
        function formatNumber(n) {
            if (!n) return '0';
            if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
            if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
            if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
            return n.toFixed(2);
        }
        
        function formatPrice(p) {
            if (!p) return '0';
            if (p >= 1000) return p.toFixed(2);
            if (p >= 1) return p.toFixed(4);
            return p.toFixed(8);
        }
        
        // Start - بارگذاری تنظیمات و شروع
        loadConfig().then(() => {
            fetchData();
            // آپدیت هر 10 ثانیه (بهینه شده)
            setInterval(fetchData, 10000);
        });
    </script>
</body>
</html>
'''

AUTOTRADE_HTML = '''
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 Whale Hunter Pro - اتوترید</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * { font-family: 'Vazirmatn', sans-serif; }
        .glass { background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(10px); }
        .live { animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    </style>
</head>
<body class="bg-gradient-to-br from-slate-950 via-purple-950 to-slate-950 text-white min-h-screen">
    
    <!-- Header -->
    <header class="glass border-b border-slate-700 sticky top-0 z-50">
        <div class="container mx-auto px-4 py-3">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-4">
                    <h1 class="text-2xl font-bold">🤖 اتوترید</h1>
                    <span id="statusBadge" class="px-3 py-1 rounded-full bg-slate-500/20 text-slate-400 text-sm">غیرفعال</span>
                </div>
                <a href="/" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg">🏠 داشبورد اصلی</a>
            </div>
        </div>
    </header>
    
    <main class="container mx-auto px-4 py-6">
        
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            <!-- Connection -->
            <div class="glass rounded-xl p-4 border border-slate-700">
                <h3 class="font-bold mb-4">🔗 اتصال به صرافی</h3>
                <div class="space-y-3">
                    <select id="exchange" class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        <option value="lbank">LBank</option>
                        <option value="bitunix">Bitunix</option>
                    </select>
                    <input type="text" id="apiKey" placeholder="API Key" 
                           class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600 font-mono text-sm">
                    <input type="password" id="secretKey" placeholder="Secret Key" 
                           class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600 font-mono text-sm">
                    <button onclick="saveKeys()" class="w-full bg-blue-600 hover:bg-blue-700 py-2 rounded-lg">💾 ذخیره</button>
                    <button onclick="testConnection()" class="w-full bg-purple-600 hover:bg-purple-700 py-2 rounded-lg">🔌 تست اتصال</button>
                    
                    <!-- Account Info -->
                    <div id="accountInfo" class="hidden mt-4 p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
                        <h4 class="font-bold text-green-400 mb-2">👤 اطلاعات حساب</h4>
                        <div class="space-y-1 text-sm">
                            <div class="flex justify-between">
                                <span class="text-slate-400">صرافی:</span>
                                <span id="accExchange">-</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-slate-400">نام:</span>
                                <span id="accName" class="text-cyan-400">-</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-slate-400">UID:</span>
                                <span id="accUid" class="font-mono text-xs">-</span>
                            </div>
                            <div class="flex justify-between border-t border-slate-600 pt-2 mt-2">
                                <span class="text-slate-400">موجودی:</span>
                                <span id="accBalance" class="text-green-400 font-bold text-lg">$0</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-slate-400">در دسترس:</span>
                                <span id="accAvailable" class="text-emerald-400">$0</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-slate-400">قفل شده:</span>
                                <span id="accLocked" class="text-orange-400">$0</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Settings -->
            <div class="glass rounded-xl p-4 border border-slate-700">
                <h3 class="font-bold mb-4">⚙️ تنظیمات معامله</h3>
                <div class="space-y-3">
                    <div>
                        <label class="text-slate-400 text-sm">مبلغ هر معامله (USDT)</label>
                        <input type="number" id="tradeAmount" value="5" min="5" 
                               class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                    </div>
                    <div>
                        <label class="text-slate-400 text-sm">اهرم</label>
                        <select id="leverage" class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                            <option value="1">1x</option>
                            <option value="3">3x</option>
                            <option value="5" selected>5x</option>
                            <option value="10">10x</option>
                            <option value="20">20x</option>
                        </select>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="text-slate-400 text-sm">حد ضرر (%)</label>
                            <input type="number" id="stopLoss" value="2" step="0.5"
                                   class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        </div>
                        <div>
                            <label class="text-slate-400 text-sm">حد سود (%)</label>
                            <input type="number" id="takeProfit" value="4" step="0.5"
                                   class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        </div>
                    </div>
                    <div>
                        <label class="text-slate-400 text-sm">کمیسیون (%)</label>
                        <input type="number" id="commission" value="0.05" step="0.01"
                               class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="text-slate-400 text-sm">حداکثر ترید/روز</label>
                            <input type="number" id="maxDaily" value="4" min="1"
                                   class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        </div>
                        <div>
                            <label class="text-slate-400 text-sm">حداکثر ضرر متوالی</label>
                            <input type="number" id="maxLosses" value="4" min="1"
                                   class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        </div>
                    </div>
                    <div>
                        <label class="text-slate-400 text-sm">حداقل امتیاز سیگنال</label>
                        <input type="number" id="minScore" value="70" min="50" max="100"
                               class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                    </div>
                    <button onclick="saveSettings()" class="w-full bg-green-600 hover:bg-green-700 py-2 rounded-lg">💾 ذخیره تنظیمات</button>
                </div>
            </div>
            
            <!-- Control -->
            <div class="glass rounded-xl p-4 border border-slate-700">
                <h3 class="font-bold mb-4">🎮 کنترل</h3>
                <div class="space-y-4">
                    <div class="p-4 bg-slate-800 rounded-lg text-center">
                        <div class="text-sm text-slate-400">وضعیت</div>
                        <div id="tradeStatus" class="text-2xl font-bold text-slate-400">غیرفعال</div>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-2">
                        <div class="p-3 bg-slate-800 rounded-lg text-center">
                            <div class="text-lg font-bold text-green-400" id="statsWins">0</div>
                            <div class="text-xs text-slate-400">موفق</div>
                        </div>
                        <div class="p-3 bg-slate-800 rounded-lg text-center">
                            <div class="text-lg font-bold text-red-400" id="statsLosses">0</div>
                            <div class="text-xs text-slate-400">ناموفق</div>
                        </div>
                    </div>
                    
                    <div class="p-3 bg-slate-800 rounded-lg">
                        <div class="flex justify-between text-sm">
                            <span>ترید امروز:</span>
                            <span id="statsDailyTrades">0</span>
                        </div>
                        <div class="flex justify-between text-sm">
                            <span>ضرر متوالی:</span>
                            <span id="statsConsecutive">0</span>
                        </div>
                        <div class="flex justify-between text-sm">
                            <span>ترید باز:</span>
                            <span id="statsOpenTrades">0</span>
                        </div>
                    </div>
                    
                    <div class="p-3 bg-slate-800 rounded-lg">
                        <div class="flex justify-between">
                            <span>سود/زیان روزانه:</span>
                            <span id="statsDailyPnl" class="font-bold text-green-400">$0</span>
                        </div>
                        <div class="flex justify-between text-sm">
                            <span>کمیسیون:</span>
                            <span id="statsDailyCommission" class="text-orange-400">$0</span>
                        </div>
                        <div class="flex justify-between text-sm">
                            <span>Win Rate:</span>
                            <span id="statsDailyWinRate" class="text-blue-400">0%</span>
                        </div>
                    </div>
                    
                    <button onclick="startAutoTrade()" id="btnStart" class="w-full bg-green-600 hover:bg-green-700 py-3 rounded-lg font-bold text-lg">
                        ▶️ شروع اتوترید
                    </button>
                    <button onclick="stopAutoTrade()" id="btnStop" class="hidden w-full bg-red-600 hover:bg-red-700 py-3 rounded-lg font-bold text-lg">
                        ⏹️ توقف
                    </button>
                </div>
            </div>
            
        </div>
        
        <!-- Trade Queue -->
        <div class="mt-6 glass rounded-xl p-4 border border-green-500/30">
            <h3 class="font-bold text-green-400 mb-4">🎯 صف اتوترید (مرتب بر امتیاز)</h3>
            <div id="tradeQueue" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                <div class="text-slate-400 text-center py-4">سیگنال معتبری وجود ندارد</div>
            </div>
        </div>
        
        <!-- Open Trades -->
        <div class="mt-6 glass rounded-xl p-4 border border-blue-500/30">
            <h3 class="font-bold text-blue-400 mb-4">📊 معاملات باز</h3>
            <div id="openTrades" class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="bg-slate-800">
                        <tr class="text-slate-400">
                            <th class="text-right py-2 px-2">نماد</th>
                            <th class="text-right py-2 px-2">نوع</th>
                            <th class="text-right py-2 px-2">قیمت ورود</th>
                            <th class="text-right py-2 px-2">SL</th>
                            <th class="text-right py-2 px-2">TP</th>
                            <th class="text-right py-2 px-2">مبلغ</th>
                            <th class="text-right py-2 px-2">اهرم</th>
                            <th class="text-right py-2 px-2">زمان</th>
                        </tr>
                    </thead>
                    <tbody id="openTradesTable"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Trade History -->
        <div class="mt-6 glass rounded-xl p-4 border border-slate-700">
            <div class="flex justify-between items-center mb-4">
                <h3 class="font-bold">📜 تاریخچه معاملات</h3>
                <a href="/api/export/trades" class="px-3 py-1 rounded bg-blue-600 text-sm">📥 CSV</a>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="bg-slate-800">
                        <tr class="text-slate-400">
                            <th class="text-right py-2 px-2">زمان</th>
                            <th class="text-right py-2 px-2">نماد</th>
                            <th class="text-right py-2 px-2">نوع</th>
                            <th class="text-right py-2 px-2">ورود</th>
                            <th class="text-right py-2 px-2">خروج</th>
                            <th class="text-right py-2 px-2">مبلغ</th>
                            <th class="text-right py-2 px-2">PnL</th>
                            <th class="text-right py-2 px-2">کمیسیون</th>
                            <th class="text-right py-2 px-2">سود خالص</th>
                        </tr>
                    </thead>
                    <tbody id="tradesTable"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Reports -->
        <div class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="glass rounded-xl p-4 border border-slate-700">
                <h3 class="font-bold mb-4">📅 گزارش روزانه</h3>
                <div class="space-y-2">
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>تعداد معاملات:</span>
                        <span id="dailyTotal">0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>موفق:</span>
                        <span id="dailyWins" class="text-green-400">0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>ناموفق:</span>
                        <span id="dailyLosses" class="text-red-400">0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>سود/زیان:</span>
                        <span id="dailyPnl" class="font-bold">$0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>کمیسیون:</span>
                        <span id="dailyCommission" class="text-orange-400">$0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>Win Rate:</span>
                        <span id="dailyWinRate" class="text-blue-400">0%</span>
                    </div>
                </div>
            </div>
            <div class="glass rounded-xl p-4 border border-slate-700">
                <h3 class="font-bold mb-4">📆 گزارش ماهانه</h3>
                <div class="space-y-2">
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>تعداد معاملات:</span>
                        <span id="monthlyTotal">0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>موفق:</span>
                        <span id="monthlyWins" class="text-green-400">0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>ناموفق:</span>
                        <span id="monthlyLosses" class="text-red-400">0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>سود/زیان:</span>
                        <span id="monthlyPnl" class="font-bold">$0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>کمیسیون:</span>
                        <span id="monthlyCommission" class="text-orange-400">$0</span>
                    </div>
                    <div class="flex justify-between p-2 bg-slate-800 rounded">
                        <span>Win Rate:</span>
                        <span id="monthlyWinRate" class="text-blue-400">0%</span>
                    </div>
                </div>
            </div>
        </div>
        
    </main>
    
    <script>
        async function fetchData() {
            try {
                // Trade Queue
                const queueRes = await fetch('/api/trade_queue');
                const queue = await queueRes.json();
                renderQueue(queue);
                
                // Trades
                const tradesRes = await fetch('/api/trades');
                const trades = await tradesRes.json();
                renderTrades(trades);
                
                // Stats
                const statsRes = await fetch('/api/trade_stats');
                const stats = await statsRes.json();
                renderStats(stats);
                
            } catch (e) {
                console.error('Fetch error:', e);
            }
        }
        
        function renderQueue(data) {
            if (!data.length) {
                document.getElementById('tradeQueue').innerHTML = '<div class="text-slate-400 text-center py-4 col-span-full">سیگنال معتبری وجود ندارد</div>';
                return;
            }
            
            document.getElementById('tradeQueue').innerHTML = data.map((s, i) => `
                <div class="p-3 rounded-lg border ${s.signal_type === 'LONG' ? 'border-green-500/30 bg-green-500/10' : 'border-red-500/30 bg-red-500/10'}">
                    <div class="flex justify-between items-center">
                        <span class="font-bold">#${i + 1} ${s.symbol.replace('USDT', '')}</span>
                        <span class="px-2 py-0.5 rounded text-xs ${s.signal_type === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">
                            ${s.signal_type}
                        </span>
                    </div>
                    <div class="flex justify-between mt-2">
                        <span class="text-slate-400 text-sm">امتیاز:</span>
                        <span class="font-bold text-lg">${s.score}</span>
                    </div>
                    <div class="w-full bg-slate-700 rounded-full h-2 mt-1">
                        <div class="bg-green-500 h-2 rounded-full" style="width: ${s.score}%"></div>
                    </div>
                </div>
            `).join('');
        }
        
        function renderTrades(data) {
            const open = data.filter(t => t.status === 'open');
            const closed = data.filter(t => t.status === 'closed');
            
            document.getElementById('openTradesTable').innerHTML = open.map(t => `
                <tr class="border-b border-slate-700">
                    <td class="py-2 px-2 font-bold">${t.symbol.replace('USDT', '')}</td>
                    <td class="py-2 px-2">
                        <span class="px-2 py-0.5 rounded text-xs ${t.side === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">
                            ${t.side}
                        </span>
                    </td>
                    <td class="py-2 px-2">$${t.entry_price.toFixed(4)}</td>
                    <td class="py-2 px-2 text-red-400">$${t.stop_loss.toFixed(4)}</td>
                    <td class="py-2 px-2 text-green-400">$${t.take_profit.toFixed(4)}</td>
                    <td class="py-2 px-2">$${t.amount}</td>
                    <td class="py-2 px-2">${t.leverage}x</td>
                    <td class="py-2 px-2 text-xs">${new Date(t.opened_at).toLocaleString('fa-IR')}</td>
                </tr>
            `).join('') || '<tr><td colspan="8" class="text-center py-4 text-slate-400">معامله باز وجود ندارد</td></tr>';
            
            document.getElementById('tradesTable').innerHTML = closed.slice(0, 20).map(t => `
                <tr class="border-b border-slate-700 ${t.net_pnl >= 0 ? 'bg-green-500/5' : 'bg-red-500/5'}">
                    <td class="py-2 px-2 text-xs">${new Date(t.closed_at).toLocaleString('fa-IR')}</td>
                    <td class="py-2 px-2 font-bold">${t.symbol.replace('USDT', '')}</td>
                    <td class="py-2 px-2">
                        <span class="px-2 py-0.5 rounded text-xs ${t.side === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">
                            ${t.side}
                        </span>
                    </td>
                    <td class="py-2 px-2">$${t.entry_price.toFixed(4)}</td>
                    <td class="py-2 px-2">$${t.exit_price.toFixed(4)}</td>
                    <td class="py-2 px-2">$${t.amount}</td>
                    <td class="py-2 px-2 ${t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}">
                        ${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}
                    </td>
                    <td class="py-2 px-2 text-orange-400">$${t.commission.toFixed(2)}</td>
                    <td class="py-2 px-2 font-bold ${t.net_pnl >= 0 ? 'text-green-400' : 'text-red-400'}">
                        ${t.net_pnl >= 0 ? '+' : ''}$${t.net_pnl.toFixed(2)}
                    </td>
                </tr>
            `).join('') || '<tr><td colspan="9" class="text-center py-4 text-slate-400">تاریخچه خالی است</td></tr>';
        }
        
        function renderStats(data) {
            // Status
            document.getElementById('tradeStatus').textContent = data.is_running ? 'فعال ✅' : 'غیرفعال';
            document.getElementById('tradeStatus').className = 'text-2xl font-bold ' + (data.is_running ? 'text-green-400' : 'text-slate-400');
            document.getElementById('statusBadge').textContent = data.is_running ? '● فعال' : '● غیرفعال';
            document.getElementById('statusBadge').className = 'px-3 py-1 rounded-full text-sm ' + 
                (data.is_running ? 'bg-green-500/20 text-green-400 live' : 'bg-slate-500/20 text-slate-400');
            
            if (data.is_running) {
                document.getElementById('btnStart').classList.add('hidden');
                document.getElementById('btnStop').classList.remove('hidden');
            } else {
                document.getElementById('btnStart').classList.remove('hidden');
                document.getElementById('btnStop').classList.add('hidden');
            }
            
            // Stats
            document.getElementById('statsWins').textContent = data.daily.wins;
            document.getElementById('statsLosses').textContent = data.daily.losses;
            document.getElementById('statsDailyTrades').textContent = data.daily_trades;
            document.getElementById('statsConsecutive').textContent = data.consecutive_losses;
            document.getElementById('statsOpenTrades').textContent = data.open_trades;
            
            const pnl = data.daily.pnl;
            document.getElementById('statsDailyPnl').textContent = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
            document.getElementById('statsDailyPnl').className = 'font-bold ' + (pnl >= 0 ? 'text-green-400' : 'text-red-400');
            document.getElementById('statsDailyCommission').textContent = '$' + data.daily.commission.toFixed(2);
            document.getElementById('statsDailyWinRate').textContent = data.daily.win_rate + '%';
            
            // Daily Report
            document.getElementById('dailyTotal').textContent = data.daily.total;
            document.getElementById('dailyWins').textContent = data.daily.wins;
            document.getElementById('dailyLosses').textContent = data.daily.losses;
            document.getElementById('dailyPnl').textContent = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
            document.getElementById('dailyPnl').className = 'font-bold ' + (pnl >= 0 ? 'text-green-400' : 'text-red-400');
            document.getElementById('dailyCommission').textContent = '$' + data.daily.commission.toFixed(2);
            document.getElementById('dailyWinRate').textContent = data.daily.win_rate + '%';
            
            // Monthly Report
            const mPnl = data.monthly.pnl;
            document.getElementById('monthlyTotal').textContent = data.monthly.total;
            document.getElementById('monthlyWins').textContent = data.monthly.wins;
            document.getElementById('monthlyLosses').textContent = data.monthly.losses;
            document.getElementById('monthlyPnl').textContent = (mPnl >= 0 ? '+' : '') + '$' + mPnl.toFixed(2);
            document.getElementById('monthlyPnl').className = 'font-bold ' + (mPnl >= 0 ? 'text-green-400' : 'text-red-400');
            document.getElementById('monthlyCommission').textContent = '$' + data.monthly.commission.toFixed(2);
            document.getElementById('monthlyWinRate').textContent = data.monthly.win_rate + '%';
        }
        
        async function testConnection() {
            const exchange = document.getElementById('exchange').value;
            const apiKey = document.getElementById('apiKey').value;
            const secretKey = document.getElementById('secretKey').value;
            
            if (!apiKey || !secretKey) {
                alert('❌ لطفاً API Key و Secret Key را وارد کنید');
                return;
            }
            
            // Save first
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    exchange: exchange,
                    api_key: apiKey,
                    secret_key: secretKey
                })
            });
            
            // Test connection
            const res = await fetch('/api/account');
            const data = await res.json();
            
            if (data.success) {
                document.getElementById('accountInfo').classList.remove('hidden');
                document.getElementById('accExchange').textContent = data.exchange;
                document.getElementById('accName').textContent = data.name;
                document.getElementById('accUid').textContent = data.uid;
                document.getElementById('accBalance').textContent = '$' + data.balance.toFixed(2);
                document.getElementById('accAvailable').textContent = '$' + data.available.toFixed(2);
                document.getElementById('accLocked').textContent = '$' + data.locked.toFixed(2);
                alert('✅ اتصال موفق!');
            } else {
                alert('❌ خطا: ' + data.error);
            }
        }
        
        async function saveKeys() {
            const exchange = document.getElementById('exchange').value;
            const apiKey = document.getElementById('apiKey').value;
            const secretKey = document.getElementById('secretKey').value;
            
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    exchange: exchange,
                    api_key: apiKey,
                    secret_key: secretKey
                })
            });
            
            alert('✅ کلیدها ذخیره شد');
        }
        
        async function saveSettings() {
            const config = {
                trade_amount: parseFloat(document.getElementById('tradeAmount').value),
                leverage: parseInt(document.getElementById('leverage').value),
                stop_loss: parseFloat(document.getElementById('stopLoss').value),
                take_profit: parseFloat(document.getElementById('takeProfit').value),
                commission: parseFloat(document.getElementById('commission').value),
                max_daily_trades: parseInt(document.getElementById('maxDaily').value),
                max_consecutive_losses: parseInt(document.getElementById('maxLosses').value),
                min_score_for_trade: parseInt(document.getElementById('minScore').value)
            };
            
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            });
            
            alert('✅ تنظیمات ذخیره شد');
        }
        
        async function startAutoTrade() {
            await fetch('/api/autotrade/start', {method: 'POST'});
            fetchData();
        }
        
        async function stopAutoTrade() {
            await fetch('/api/autotrade/stop', {method: 'POST'});
            fetchData();
        }
        
        // Start
        fetchData();
        setInterval(fetchData, 5000);
    </script>
</body>
</html>
'''

# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("🐋 Whale Hunter Pro v6.0")
    print("=" * 60)
    print()
    print("📊 داشبورد کنترلی:  http://localhost:5000")
    print("🤖 داشبورد اتوترید: http://localhost:5000/autotrade")
    print()
    print("=" * 60)
    
    # Initialize
    init_db()
    worker_thread.start()
    
    # Run Flask
    app.run(host='0.0.0.0', port=5000, debug=False)
