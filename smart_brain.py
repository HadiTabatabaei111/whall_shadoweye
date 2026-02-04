# smart_brain.py
import time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from fastapi import FastAPI
import uvicorn

# =========================
# 1) مدل مغز هوشمند
# =========================

class GlobalEncoder(nn.Module):
    def __init__(self, btc_dim, hidden=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(btc_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 64),
            nn.ReLU()
        )

    def forward(self, x_btc):
        return self.net(x_btc)


class LocalEncoder(nn.Module):
    def __init__(self, alt_dim, hidden=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(alt_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 32),
            nn.ReLU()
        )

    def forward(self, x_alt):
        return self.net(x_alt)


class AttentionFusion(nn.Module):
    def __init__(self, g_dim=64, l_dim=32):
        super().__init__()
        self.attn = nn.Linear(g_dim + l_dim, 2)

    def forward(self, g, l):
        x = torch.cat([g, l], dim=-1)
        w = F.softmax(self.attn(x), dim=-1)  # [batch, 2]
        g_w = w[:, 0:1]
        l_w = w[:, 1:2]
        fused = g_w * g + l_w * l
        return fused


class PolicyNet(nn.Module):
    def __init__(self, btc_dim, alt_dim, action_dim=3):
        super().__init__()
        self.global_enc = GlobalEncoder(btc_dim)
        self.local_enc  = LocalEncoder(alt_dim)
        self.fusion     = AttentionFusion()
        self.head       = nn.Sequential(
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, action_dim)  # 0=HOLD,1=BUY,2=SELL
        )

    def forward(self, btc_features, alt_features):
        g = self.global_enc(btc_features)
        l = self.local_enc(alt_features)
        fused = self.fusion(g, l)
        logits = self.head(fused)
        return logits


# =========================
# 2) DataSource (ورودی از مارکت)
# اینجا فعلاً mock است؛ بعداً وصلش می‌کنی به Bybit/OKX/Coinglass
# =========================

class DataSource:
    def __init__(self):
        self.t = 0

    def get_btc_features_live(self):
        # TODO: اینجا رو به Bybit/OKX/Coinglass وصل کن
        # فعلاً داده‌ی تصادفی برای تست
        btc_ret_1m = np.random.normal(0, 0.001)
        btc_ret_5m = np.random.normal(0, 0.002)
        btc_vol_1h = np.random.rand()
        btc_funding = np.random.normal(0, 0.0001)
        btc_oi = np.random.rand()
        btc_ls = np.random.rand()
        return np.array([
            btc_ret_1m,
            btc_ret_5m,
            btc_vol_1h,
            btc_funding,
            btc_oi,
            btc_ls
        ], dtype=np.float32)

    def get_alt_features_live(self, symbol: str):
        # TODO: اینجا رو به Bybit/LBank/OKX وصل کن
        alt_ret_1m = np.random.normal(0, 0.002)
        alt_ret_5m = np.random.normal(0, 0.004)
        alt_vol_1h = np.random.rand()
        alt_rsi = np.random.uniform(0, 100)
        alt_ema_fast = np.random.rand()
        alt_ema_slow = np.random.rand()
        return np.array([
            alt_ret_1m,
            alt_ret_5m,
            alt_vol_1h,
            alt_rsi / 100.0,
            alt_ema_fast,
            alt_ema_slow
        ], dtype=np.float32)


# =========================
# 3) Broker (خروجی به صرافی)
# فعلاً فقط log می‌کند؛ بعداً به Bybit/LBank وصلش می‌کنی
# =========================

class Broker:
    def __init__(self, name="paper"):
        self.name = name

    def execute(self, symbol: str, action: str, size: float):
        # TODO: اینجا رو به API واقعی Bybit/LBank وصل کن
        print(f"[BROKER-{self.name}] {symbol} | {action} | size={size}")


# =========================
# 4) محیط ساده برای RL / تست
# =========================

class TradingEnv:
    def __init__(self, data_source: DataSource):
        self.data_source = data_source
        self.position = 0.0
        self.price_prev = 100.0

    def get_state_live(self, symbol: str):
        btc = self.data_source.get_btc_features_live()
        alt = self.data_source.get_alt_features_live(symbol)
        return btc, alt

    def compute_reward(self, position, price_now, price_prev, fee=0.0,
                       alpha=1.0, beta=0.0, gamma=0.0):
        pnl = position * (price_now - price_prev)
        reward = alpha * pnl - beta * 0.0 - gamma * fee
        return reward


# =========================
# 5) نمونه‌ی ساده‌ی inference (بدون آموزش)
# =========================

BTC_DIM = 6
ALT_DIM = 6
ACTIONS = ["HOLD", "BUY", "SELL"]

data_source = DataSource()
env = TradingEnv(data_source)
broker = Broker(name="paper")

device = torch.device("cpu")

model = PolicyNet(btc_dim=BTC_DIM, alt_dim=ALT_DIM, action_dim=len(ACTIONS)).to(device)
model.eval()  # فعلاً بدون آموزش، فقط تست جریان


def get_signal(symbol: str):
    btc_f = data_source.get_btc_features_live()
    alt_f = data_source.get_alt_features_live(symbol)

    btc_t = torch.tensor(btc_f, dtype=torch.float32, device=device).unsqueeze(0)
    alt_t = torch.tensor(alt_f, dtype=torch.float32, device=device).unsqueeze(0)

    with torch.no_grad():
        logits = model(btc_t, alt_t)
        probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]
        action_idx = int(np.argmax(probs))
        action = ACTIONS[action_idx]

    return {
        "symbol": symbol,
        "action": action,
        "probs": probs.tolist(),
        "timestamp": int(time.time())
    }


# =========================
# 6) API برای داشبورد و اتوترید
# =========================

app = FastAPI()

@app.get("/signal")
def api_get_signal(symbol: str = "ETHUSDT"):
    sig = get_signal(symbol)
    return sig

@app.post("/autotrade")
def api_autotrade(symbol: str = "ETHUSDT", size: float = 0.01):
    sig = get_signal(symbol)
    action = sig["action"]
    if action != "HOLD":
        broker.execute(symbol, action, size)
    return {
        "executed": action != "HOLD",
        "signal": sig
    }


if __name__ == "__main__":
    # اجرای API برای تست سریع
    uvicorn.run(app, host="0.0.0.0", port=8000)