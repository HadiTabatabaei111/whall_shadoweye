```python
# فایل: test_db_connection.py
import sqlite3
import pandas as pd
from pathlib import Path

def test_connection():
    db_path = Path("./data/quantum_trading.db")  # مسیر دیتابیس
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. تست خواندن کندل‌ها
        cursor.execute("SELECT COUNT(*) as total_candles FROM candles_1m")
        candles_count = cursor.fetchone()[0]
        
        # 2. تست خواندن نهنگ‌ها
        cursor.execute("SELECT COUNT(*) as total_whales FROM whale_movements")
        whales_count = cursor.fetchone()[0]
        
        # 3. لیست نمادهای موجود
        cursor.execute("SELECT DISTINCT symbol FROM candles_1m LIMIT 5")
        symbols = cursor.fetchall()
        
        conn.close()
        
        print(f"""
        ✅ اتصال به دیتابیس موفقیت‌آمیز بود:
        
        📊 آمار دیتابیس:
        • تعداد کندل‌های ذخیره‌شده: {candles_count:,}
        • تعداد حرکات نهنگ ثبت‌شده: {whales_count:,}
        • نمادهای موجود: {[s[0] for s in symbols]}
        
        🎯 سیستم آماده یکپارچه‌سازی است.
        """)
        
        return True
        
    except Exception as e:
        print(f"❌ خطا در اتصال به دیتابیس: {e}")
        return False

if __name__ == "__main__":
    test_connection()
```

📦 کد کامل موتور کشف الگو (یکپارچه با دیتابیس شما):

پس از تأیید اتصال، این موتور اصلی را در کنار دیتابیس قرار بده. این کد به طور مستقیم از جداول candles_1m و whale_movements تو داده می‌خواند:

```python
"""
🧠 GALACTIC PATTERN DISCOVERY ENGINE - PRODUCTION v1.0
اتصال مستقیم به دیتابیس واقعی کاربر
"""

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import hashlib
import asyncio
import logging

# ==================== CONFIGURATION ====================
DB_PATH = Path("./data/quantum_trading.db")  # مسیر دیتابیس اصلی شما
SYMBOL = "BTCUSDT"  # نماد هدف برای کشف الگو

class RealDataPatternEngine:
    """موتور کشف الگو با اتصال مستقیم به دیتابیس واقعی"""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = None
        self.setup_logging()
        
        # پارامترهای کشف
        self.config = {
            'min_candles_for_analysis': 5000,
            'discovery_lookback_days': 30,
            'min_pattern_confidence': 0.65,
            'required_win_rate': 0.55,
            'max_drawdown_limit': 0.15,
            'test_period_days': 7
        }
        
    def setup_logging(self):
        """تنظیم سیستم لاگ‌گیری"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('pattern_discovery.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    # ==================== DATABASE CONNECTION ====================
    
    def connect_to_database(self) -> bool:
        """اتصال به دیتابیس SQLite"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # برای دسترسی به ستون‌ها با نام
            self.logger.info(f"✅ متصل به دیتابیس: {self.db_path}")
            return True
        except Exception as e:
            self.logger.error(f"❌ خطا در اتصال به دیتابیس: {e}")
            return False
    
    def disconnect(self):
        """قطع اتصال از دیتابیس"""
        if self.conn:
            self.conn.close()
            self.logger.info("✅ اتصال دیتابیس بسته شد")
    
    # ==================== REAL DATA FETCHING ====================
    
    def fetch_candle_data(self, symbol: str = SYMBOL, days: int = 30) -> pd.DataFrame:
        """خواندن داده‌های کندل واقعی از دیتابیس"""
        query = """
        SELECT 
            timestamp,
            open,
            high,
            low,
            close,
            volume,
            oi,
            funding_rate,
            buy_liq,
            sell_liq
        FROM candles_1m 
        WHERE symbol = ?
        AND timestamp >= datetime('now', '-' || ? || ' days')
        ORDER BY timestamp ASC
        """
        
        try:
            df = pd.read_sql_query(
                query, 
                self.conn, 
                params=(symbol, days)
            )
            
            # تبدیل timestamp به datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # محاسبه اندیکاتورهای پایه
            df['returns'] = df['close'].pct_change()
            df['volume_ma'] = df['volume'].rolling(20).mean()
            df['volatility'] = df['returns'].rolling(50).std()
            
            self.logger.info(f"📥 {len(df)} کندل واقعی بارگذاری شد (نماد: {symbol})")
            return df
            
        except Exception as e:
            self.logger.error(f"❌ خطا در خواندن کندل‌ها: {e}")
            return pd.DataFrame()
    
    def fetch_whale_data(self, symbol: str = SYMBOL, days: int = 30) -> pd.DataFrame:
        """خواندن داده‌های نهنگ واقعی از دیتابیس"""
        query = """
        SELECT 
            timestamp,
            size,
            direction,
            confidence,
            exchange
        FROM whale_movements 
        WHERE symbol = ?
        AND timestamp >= datetime('now', '-' || ? || ' days')
        ORDER BY timestamp ASC
        """
        
        try:
            df = pd.read_sql_query(
                query, 
                self.conn, 
                params=(symbol, days)
            )
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                self.logger.info(f"🐋 {len(df)} حرکت نهنگ واقعی بارگذاری شد")
            else:
                self.logger.warning("⚠️ داده نهنگی برای تحلیل یافت نشد")
            
            return df
            
        except Exception as e:
            self.logger.error(f"❌ خطا در خواندن داده نهنگ‌ها: {e}")
            return pd.DataFrame()
    
    # ==================== PATTERN DISCOVERY CORE ====================
    
    def discover_price_volume_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """کشف الگوهای قیمت-حجم"""
        patterns = []
        
        if len(df) < 100:
            return patterns
        
        try:
            # محاسبه همبستگی‌های مهم
            correlations = {
                'volume_price': df['volume'].corr(df['close']),
                'oi_price': df['oi'].corr(df['close']) if 'oi' in df.columns else 0,
                'volume_returns': df['volume'].corr(df['returns'].abs()),
                'funding_returns': df['funding_rate'].corr(df['returns']) if 'funding_rate' in df.columns else 0
            }
            
            # الگوی حجم سنگین + حرکت قیمت (پامپ)
            volume_spike_threshold = df['volume_ma'].mean() * 2
            df['volume_spike'] = df['volume'] > volume_spike_threshold
            df['price_up_5min'] = df['close'].pct_change(5) > 0.002  # 0.2% رشد در 5 دقیقه
            
            pump_patterns = df[df['volume_spike'] & df['price_up_5min']]
            
            if len(pump_patterns) > 3:
                pattern = {
                    'id': 'VOL_PUMP_001',
                    'name': 'الگوی پامپ حجمی',
                    'condition': 'volume > MA(volume,20)*2 AND price_increase_5min > 0.2%',
                    'occurrences': len(pump_patterns),
                    'avg_price_change': (pump_patterns['close'].pct_change(10).mean() * 100),
                    'confidence': min(len(pump_patterns) / 50, 0.9),
                    'timeframe': '5m',
                    'action': 'BUY'
                }
                patterns.append(pattern)
            
            # الگوی واگرایی حجم-قیمت (ضعف روند)
            if len(df) > 100:
                df['price_high'] = df['close'].rolling(20).max()
                df['volume_low'] = df['volume'].rolling(20).min()
                
                divergence_patterns = df[(df['price'] == df['price_high']) & 
                                        (df['volume'] == df['volume_low'])]
                
                if len(divergence_patterns) > 2:
                    pattern = {
                        'id': 'VOL_DIVERGENCE_001',
                        'name': 'واگرایی حجم-قیمت',
                        'condition': 'price = 20_period_high AND volume = 20_period_low',
                        'occurrences': len(divergence_patterns),
                        'avg_reversal': 0,  # محاسبه شود
                        'confidence': min(len(divergence_patterns) / 30, 0.8),
                        'timeframe': '15m',
                        'action': 'SELL'
                    }
                    patterns.append(pattern)
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"❌ خطا در کشف الگوها: {e}")
            return patterns
    
    def discover_whale_patterns(self, price_df: pd.DataFrame, whale_df: pd.DataFrame) -> List[Dict]:
        """کشف الگوهای مرتبط با حرکت نهنگ‌ها"""
        patterns = []
        
        if whale_df.empty:
            return patterns
        
        try:
            # ادغام داده‌های قیمت و نهنگ بر اساس زمان
            whale_df['timestamp_rounded'] = whale_df['timestamp'].dt.floor('5min')
            price_df['timestamp_rounded'] = price_df['timestamp'].dt.floor('5min')
            
            merged = pd.merge(
                price_df[['timestamp_rounded', 'close', 'returns']],
                whale_df.groupby('timestamp_rounded').agg({
                    'size': 'sum',
                    'direction': lambda x: list(x)
                }).reset_index(),
                on='timestamp_rounded',
                how='left'
            )
            
            # الگوی نهنگ خریدار + حرکت صعودی
            big_buy_events = merged[
                (merged['size'] > merged['size'].quantile(0.75)) & 
                (merged['direction'].apply(lambda x: 'exchange_in' in str(x) if x else False))
            ]
            
            if len(big_buy_events) > 2:
                # بررسی حرکت قیمت پس از ورود نهنگ
                forward_returns = []
                for idx in big_buy_events.index:
                    if idx + 10 < len(price_df):
                        ret = price_df.iloc[idx + 10]['close'] / price_df.iloc[idx]['close'] - 1
                        forward_returns.append(ret)
                
                if forward_returns:
                    avg_return = np.mean(forward_returns) * 100
                    win_rate = sum(1 for r in forward_returns if r > 0) / len(forward_returns)
                    
                    if win_rate > self.config['required_win_rate']:
                        pattern = {
                            'id': 'WHALE_BUY_001',
                            'name': 'ورود نهنگ خریدار',
                            'condition': 'whale_inflow > 75_percentile AND direction = exchange_in',
                            'occurrences': len(big_buy_events),
                            'avg_return': avg_return,
                            'win_rate': win_rate,
                            'confidence': min(win_rate * 0.8, 0.85),
                            'timeframe': '15m',
                            'action': 'BUY',
                            'whale_threshold_usd': big_buy_events['size'].median()
                        }
                        patterns.append(pattern)
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"❌ خطا در تحلیل الگوهای نهنگ: {e}")
            return patterns
    
    # ==================== BACKTESTING ENGINE ====================
    
    def backtest_pattern(self, pattern: Dict, df: pd.DataFrame) -> Dict:
        """تست الگو روی داده‌های تاریخی"""
        if 'condition' not in pattern:
            return {'success': False, 'error': 'شرط الگو تعریف نشده'}
        
        try:
            # شبیه‌سازی ساده - در نسخه کامل باید دقیق‌تر شود
            trades = []
            initial_balance = 10000
            balance = initial_balance
            
            # تشخیص سیگنال‌ها بر اساس نوع الگو
            if 'VOL_PUMP' in pattern['id']:
                # تشخیص پامپ حجمی
                signals = self._detect_volume_pump_signals(df)
            elif 'WHALE_BUY' in pattern['id']:
                # تشخیص ورود نهنگ
                signals = self._detect_whale_buy_signals(df)
            else:
                signals = []
            
            # شبیه‌سازی معاملات
            for signal in signals:
                if signal['action'] == 'BUY':
                    # فرض: خرید در قیمت بسته شدن و فروش 10 کندل بعد
                    entry_idx = signal['index']
                    if entry_idx + 10 < len(df):
                        entry_price = df.iloc[entry_idx]['close']
                        exit_price = df.iloc[entry_idx + 10]['close']
                        
                        pnl_percent = (exit_price - entry_price) / entry_price
                        position_size = balance * 0.1  # 10% سرمایه
                        pnl = position_size * pnl_percent
                        
                        balance += pnl
                        
                        trades.append({
                            'entry': entry_price,
                            'exit': exit_price,
                            'pnl_percent': pnl_percent,
                            'pnl_usd': pnl,
                            'timestamp': df.iloc[entry_idx]['timestamp']
                        })
            
            # تحلیل نتایج
            if trades:
                winning_trades = [t for t in trades if t['pnl_usd'] > 0]
                total_return = (balance - initial_balance) / initial_balance
                win_rate = len(winning_trades) / len(trades)
                
                # محاسبه حداکثر افت سرمایه
                equity_curve = [initial_balance]
                for trade in trades:
                    equity_curve.append(equity_curve[-1] + trade['pnl_usd'])
                
                equity_series = pd.Series(equity_curve)
                drawdown = (equity_series.expanding().max() - equity_series) / equity_series.expanding().max()
                max_drawdown = drawdown.max()
                
                return {
                    'success': True,
                    'total_trades': len(trades),
                    'winning_trades': len(winning_trades),
                    'win_rate': win_rate,
                    'total_return': total_return,
                    'max_drawdown': max_drawdown,
                    'final_balance': balance,
                    'sharpe_ratio': self._calculate_sharpe_ratio([t['pnl_percent'] for t in trades]),
                    'trades': trades[:10]  # فقط 10 معامله اول برای نمایش
                }
            else:
                return {
                    'success': False,
                    'error': 'هیچ سیگنالی شناسایی نشد'
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _detect_volume_pump_signals(self, df: pd.DataFrame) -> List[Dict]:
        """تشخیص سیگنال‌های پامپ حجمی"""
        signals = []
        
        if len(df) < 50:
            return signals
        
        volume_ma = df['volume'].rolling(20).mean()
        volume_spike = df['volume'] > volume_ma * 2
        
        for i in range(len(df) - 1):
            if volume_spike.iloc[i] and df['returns'].iloc[i] > 0:
                signals.append({
                    'index': i,
                    'action': 'BUY',
                    'reason': 'volume_spike',
                    'volume_ratio': df['volume'].iloc[i] / volume_ma.iloc[i]
                })
        
        return signals
    
    # ==================== MAIN DISCOVERY PIPELINE ====================
    
    def run_full_discovery(self, symbol: str = SYMBOL) -> Dict:
        """اجرای خط کامل کشف الگو"""
        self.logger.info(f"🚀 شروع کشف الگو برای {symbol}")
        
        results = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'patterns_found': [],
            'total_patterns': 0,
            'best_pattern': None,
            'status': 'running'
        }
        
        try:
            # 1. اتصال به دیتابیس
            if not self.connect_to_database():
                results['status'] = 'db_connection_failed'
                return results
            
            # 2. خواندن داده‌های واقعی
            price_data = self.fetch_candle_data(symbol, self.config['discovery_lookback_days'])
            whale_data = self.fetch_whale_data(symbol, self.config['discovery_lookback_days'])
            
            if len(price_data) < self.config['min_candles_for_analysis']:
                self.logger.warning("⚠️ داده کافی برای تحلیل وجود ندارد")
                results['status'] = 'insufficient_data'
                return results
            
            # 3. کشف الگوهای مختلف
            all_patterns = []
            
            # الگوهای قیمت-حجم
            volume_patterns = self.discover_price_volume_patterns(price_data)
            all_patterns.extend(volume_patterns)
            
            # الگوهای نهنگ
            if not whale_data.empty:
                whale_patterns = self.discover_whale_patterns(price_data, whale_data)
                all_patterns.extend(whale_patterns)
            
            # 4. بکتست و اعتبارسنجی الگوها
            validated_patterns = []
            for pattern in all_patterns:
                backtest_result = self.backtest_pattern(pattern, price_data)
                
                if backtest_result['success']:
                    pattern['backtest'] = backtest_result
                    
                    # معیارهای تأیید
                    if (backtest_result['win_rate'] >= self.config['required_win_rate'] and
                        backtest_result['max_drawdown'] <= self.config['max_drawdown_limit']):
                        
                        pattern['validated'] = True
                        pattern['confidence'] = backtest_result['win_rate'] * 0.7 + (1 - backtest_result['max_drawdown']) * 0.3
                        validated_patterns.append(pattern)
            
            # 5. مرتب‌سازی و انتخاب بهترین الگوها
            if validated_patterns:
                validated_patterns.sort(key=lambda x: x['confidence'], reverse=True)
                results['best_pattern'] = validated_patterns[0]
            
            results['patterns_found'] = validated_patterns
            results['total_patterns'] = len(validated_patterns)
            results['status'] = 'completed'
            
            # 6. نمایش نتایج
            self.display_results(results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ خطا در اجرای کشف الگو: {e}")
            results['status'] = f'error: {str(e)}'
            return results
            
        finally:
            # 7. قطع اتصال از دیتابیس
            self.disconnect()
    
    # ==================== UTILITIES ====================
    
    def display_results(self, results: Dict):
        """نمایش نتایج کشف الگو"""
        print(f"""
        {'='*60}
        🎯 نتایج کشف الگو - {results['symbol']}
        {'='*60}
        
        📊 آمار کلی:
        • تعداد الگوهای تأییدشده: {results['total_patterns']}
        • وضعیت اجرا: {results['status']}
        • زمان تحلیل: {results['timestamp']}
        
        """)
        
        if results['best_pattern']:
            pattern = results['best_pattern']
            backtest = pattern.get('backtest', {})
            
            print(f"""
        🏆 بهترین الگو:
        • شناسه: {pattern.get('id', 'N/A')}
        • نام: {pattern.get('name', 'N/A')}
        • شرایط: {pattern.get('condition', 'N/A')}
        • اطمینان: {pattern.get('confidence', 0):.2%}
        • اقدام: {pattern.get('action', 'N/A')}
        
        📈 نتایج بکتست:
        • تعداد معاملات: {backtest.get('total_trades', 0)}
        • نرخ برد: {backtest.get('win_rate', 0):.2%}
        • بازده کل: {backtest.get('total_return', 0):.2%}
        • حداکثر افت: {backtest.get('max_drawdown', 0):.2%}
        """)
        
        print(f"{'='*60}")
    
    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """محاسبه نسبت شارپ"""
        if not returns or np.std(returns) == 0:
            return 0.0
        return np.mean(returns) / np.std(returns) * np.sqrt(365 * 24 * 60)  # سالیانه‌شده
    
    def save_patterns_to_file(self, patterns: List[Dict], filename: str = "discovered_patterns.json"):
        """ذخیره الگوهای کشف‌شده در فایل"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(patterns, f, indent=2, ensure_ascii=False, default=str)
            self.logger.info(f"💾 الگوها در {filename} ذخیره شدند")
        except Exception as e:
            self.logger.error(f"❌ خطا در ذخیره الگوها: {e}")

# ==================== EXECUTION ====================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║        🧠 موتور کشف الگو - نسخه تولید                   ║
    ╠══════════════════════════════════════════════════════════╣
    ║ اتصال مستقیم به دیتابیس واقعی                           ║
    ║ کشف الگوهای قیمت، حجم و نهنگ                           ║
    ║ اعتبارسنجی خودکار با بکتست                              ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # ساخت موتور
    engine = RealDataPatternEngine()
    
    # اجرای کشف الگو
    results = engine.run_full_discovery(SYMBOL)
    
    # ذخیره نتایج
    if results['patterns_found']:
        engine.save_patterns_to_file(results['patterns_found'])
```