/*
══════════════════════════════════════════════════════════════
   🐋 Whale Hunter Pro v5.0 - Go Edition
   سیستم رصد نهنگ مادر و اتو ترید
   
   برای اجرا:
   go run whale_hunter.go
   
   یا ساخت فایل اجرایی:
   go build whale_hunter.go
   ./whale_hunter
══════════════════════════════════════════════════════════════
*/

package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"log"
	"math"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

// ═══════════════════════════════════════════════════════════════
// تنظیمات پارامتریک
// ═══════════════════════════════════════════════════════════════

type Config struct {
	// API Settings
	APISource      string `json:"api_source"`
	AutoSwitchAPI  bool   `json:"auto_switch_api"`

	// Whale Settings
	WhaleThreshold float64 `json:"whale_threshold"`
	PumpThreshold  float64 `json:"pump_threshold"`

	// Validation Settings
	ValidationTimes   []int   `json:"validation_times"`
	ValidationWeights []int   `json:"validation_weights"`
	MinPriceChange    float64 `json:"min_price_change"`

	// Indicators
	UseRSI         bool `json:"use_rsi"`
	RSIPeriod      int  `json:"rsi_period"`
	RSIOverbought  int  `json:"rsi_overbought"`
	RSIOversold    int  `json:"rsi_oversold"`
	UseMACD        bool `json:"use_macd"`
	MACDFast       int  `json:"macd_fast"`
	MACDSlow       int  `json:"macd_slow"`
	MACDSignal     int  `json:"macd_signal"`
	UseVolume      bool `json:"use_volume"`
	VolumeMultiplier float64 `json:"volume_multiplier"`

	// Auto Trade
	Exchange       string  `json:"exchange"`
	APIKey         string  `json:"api_key"`
	SecretKey      string  `json:"secret_key"`
	TradeAmount    float64 `json:"trade_amount"`
	Leverage       int     `json:"leverage"`
	StopLoss       float64 `json:"stop_loss"`
	TakeProfit     float64 `json:"take_profit"`
	Commission     float64 `json:"commission"`

	// Risk Management
	MaxDailyTrades       int `json:"max_daily_trades"`
	MaxConsecutiveLosses int `json:"max_consecutive_losses"`
	MinScoreForTrade     int `json:"min_score_for_trade"`
}

var config = Config{
	APISource:            "coingecko",
	AutoSwitchAPI:        false,
	WhaleThreshold:       500000,
	PumpThreshold:        3,
	ValidationTimes:      []int{1, 2, 4},
	ValidationWeights:    []int{20, 30, 50},
	MinPriceChange:       0.1,
	UseRSI:               true,
	RSIPeriod:            14,
	RSIOverbought:        70,
	RSIOversold:          30,
	UseMACD:              true,
	MACDFast:             12,
	MACDSlow:             26,
	MACDSignal:           9,
	UseVolume:            true,
	VolumeMultiplier:     2,
	Exchange:             "lbank",
	TradeAmount:          5,
	Leverage:             5,
	StopLoss:             2,
	TakeProfit:           4,
	Commission:           0.05,
	MaxDailyTrades:       4,
	MaxConsecutiveLosses: 4,
	MinScoreForTrade:     70,
}

// ═══════════════════════════════════════════════════════════════
// مدل‌های داده
// ═══════════════════════════════════════════════════════════════

type MarketData struct {
	Symbol    string  `json:"symbol"`
	Price     float64 `json:"price"`
	Change    float64 `json:"change"`
	High      float64 `json:"high"`
	Low       float64 `json:"low"`
	Volume    float64 `json:"volume"`
	MarketCap float64 `json:"market_cap"`
	Timestamp string  `json:"timestamp"`
	Source    string  `json:"source"`
}

type Whale struct {
	ID              int64   `json:"id"`
	Symbol          string  `json:"symbol"`
	Price           float64 `json:"price"`
	Volume          float64 `json:"volume"`
	ChangePercent   float64 `json:"change_percent"`
	WhaleType       string  `json:"whale_type"`
	IsReal          bool    `json:"is_real"`
	ConfidenceScore float64 `json:"confidence_score"`
	Timestamp       string  `json:"timestamp"`
}

type Signal struct {
	ID             int64     `json:"id"`
	Symbol         string    `json:"symbol"`
	SignalType     string    `json:"signal_type"`
	EntryPrice     float64   `json:"entry_price"`
	Price1Min      float64   `json:"price_1min"`
	Price2Min      float64   `json:"price_2min"`
	Price4Min      float64   `json:"price_4min"`
	Change1Min     float64   `json:"change_1min"`
	Change2Min     float64   `json:"change_2min"`
	Change4Min     float64   `json:"change_4min"`
	Valid1Min      bool      `json:"valid_1min"`
	Valid2Min      bool      `json:"valid_2min"`
	Valid4Min      bool      `json:"valid_4min"`
	FinalStatus    string    `json:"final_status"`
	Score          int       `json:"score"`
	Volume         float64   `json:"volume"`
	RSI            float64   `json:"rsi"`
	MACD           float64   `json:"macd"`
	MACDSignal     float64   `json:"macd_signal"`
	MACDHistogram  float64   `json:"macd_histogram"`
	Trend          string    `json:"trend"`
	WhaleFlow      string    `json:"whale_flow"`
	Timestamp      string    `json:"timestamp"`
	ValidatedAt    string    `json:"validated_at"`
}

type Trade struct {
	ID          int64   `json:"id"`
	SignalID    int64   `json:"signal_id"`
	Symbol      string  `json:"symbol"`
	Side        string  `json:"side"`
	EntryPrice  float64 `json:"entry_price"`
	ExitPrice   float64 `json:"exit_price"`
	Amount      float64 `json:"amount"`
	Leverage    int     `json:"leverage"`
	PnL         float64 `json:"pnl"`
	PnLPercent  float64 `json:"pnl_percent"`
	Commission  float64 `json:"commission"`
	NetPnL      float64 `json:"net_pnl"`
	Status      string  `json:"status"`
	StopLoss    float64 `json:"stop_loss"`
	TakeProfit  float64 `json:"take_profit"`
	Exchange    string  `json:"exchange"`
	OpenedAt    string  `json:"opened_at"`
	ClosedAt    string  `json:"closed_at"`
}

type PumpDump struct {
	ID            int64   `json:"id"`
	Symbol        string  `json:"symbol"`
	Price         float64 `json:"price"`
	PrevPrice     float64 `json:"prev_price"`
	ChangePercent float64 `json:"change_percent"`
	EventType     string  `json:"event_type"`
	Volume        float64 `json:"volume"`
	Timestamp     string  `json:"timestamp"`
}

type WhaleFlow struct {
	Inflow  float64 `json:"inflow"`
	Outflow float64 `json:"outflow"`
	Net     float64 `json:"net"`
}

type AccountInfo struct {
	Success   bool    `json:"success"`
	Exchange  string  `json:"exchange"`
	Name      string  `json:"name"`
	UID       string  `json:"uid"`
	Balance   float64 `json:"balance"`
	Available float64 `json:"available"`
	Locked    float64 `json:"locked"`
	Error     string  `json:"error,omitempty"`
}

type TradeStats struct {
	TotalTrades     int     `json:"total_trades"`
	Wins            int     `json:"wins"`
	Losses          int     `json:"losses"`
	WinRate         float64 `json:"win_rate"`
	TotalPnL        float64 `json:"total_pnl"`
	TotalCommission float64 `json:"total_commission"`
}

type SignalStats struct {
	Valid    int     `json:"valid"`
	Invalid  int     `json:"invalid"`
	Pending  int     `json:"pending"`
	Accuracy float64 `json:"accuracy"`
}

// ═══════════════════════════════════════════════════════════════
// دیتابیس SQLite
// ═══════════════════════════════════════════════════════════════

var db *sql.DB
var dbMutex sync.Mutex

func initDB() {
	var err error
	db, err = sql.Open("sqlite3", "./whale_hunter.db")
	if err != nil {
		log.Fatal(err)
	}

	// ایجاد جداول
	tables := `
	CREATE TABLE IF NOT EXISTS whales (
		id INTEGER PRIMARY KEY,
		symbol TEXT,
		price REAL,
		volume REAL,
		change_percent REAL,
		whale_type TEXT,
		is_real INTEGER DEFAULT 1,
		confidence_score REAL DEFAULT 0,
		timestamp TEXT,
		saved_at TEXT
	);

	CREATE TABLE IF NOT EXISTS signals (
		id INTEGER PRIMARY KEY,
		symbol TEXT,
		signal_type TEXT,
		entry_price REAL,
		price_1min REAL,
		price_2min REAL,
		price_4min REAL,
		change_1min REAL,
		change_2min REAL,
		change_4min REAL,
		valid_1min INTEGER,
		valid_2min INTEGER,
		valid_4min INTEGER,
		final_status TEXT DEFAULT 'pending',
		score INTEGER DEFAULT 0,
		volume REAL,
		rsi REAL,
		macd REAL,
		macd_signal REAL,
		macd_histogram REAL,
		trend TEXT,
		whale_flow TEXT,
		timestamp TEXT,
		validated_at TEXT,
		saved_at TEXT
	);

	CREATE TABLE IF NOT EXISTS trades (
		id INTEGER PRIMARY KEY,
		signal_id INTEGER,
		symbol TEXT,
		side TEXT,
		entry_price REAL,
		exit_price REAL,
		amount REAL,
		leverage INTEGER,
		pnl REAL,
		pnl_percent REAL,
		commission REAL,
		net_pnl REAL,
		status TEXT DEFAULT 'open',
		stop_loss REAL,
		take_profit REAL,
		exchange TEXT,
		opened_at TEXT,
		closed_at TEXT,
		saved_at TEXT
	);

	CREATE TABLE IF NOT EXISTS pump_dumps (
		id INTEGER PRIMARY KEY,
		symbol TEXT,
		price REAL,
		prev_price REAL,
		change_percent REAL,
		event_type TEXT,
		volume REAL,
		timestamp TEXT,
		saved_at TEXT
	);

	CREATE TABLE IF NOT EXISTS ohlcv (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		symbol TEXT,
		timeframe TEXT,
		open_price REAL,
		high_price REAL,
		low_price REAL,
		close_price REAL,
		volume REAL,
		timestamp TEXT,
		saved_at TEXT,
		UNIQUE(symbol, timeframe, timestamp)
	);

	CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
	CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(final_status);
	CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
	`

	_, err = db.Exec(tables)
	if err != nil {
		log.Fatal(err)
	}

	log.Println("✅ دیتابیس SQLite آماده")
}

// ═══════════════════════════════════════════════════════════════
// دریافت قیمت از API
// ═══════════════════════════════════════════════════════════════

var previousPrices = make(map[string]float64)
var pricesMutex sync.RWMutex

func fetchCoinGecko() ([]MarketData, error) {
	url := "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&sparkline=false&price_change_percentage=24h"
	
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	
	var data []struct {
		Symbol                  string  `json:"symbol"`
		CurrentPrice            float64 `json:"current_price"`
		PriceChangePercentage24h float64 `json:"price_change_percentage_24h"`
		High24h                 float64 `json:"high_24h"`
		Low24h                  float64 `json:"low_24h"`
		TotalVolume             float64 `json:"total_volume"`
		MarketCap               float64 `json:"market_cap"`
	}

	if err := json.Unmarshal(body, &data); err != nil {
		return nil, err
	}

	var result []MarketData
	timestamp := time.Now().Format(time.RFC3339)
	
	for _, d := range data {
		result = append(result, MarketData{
			Symbol:    strings.ToUpper(d.Symbol) + "USDT",
			Price:     d.CurrentPrice,
			Change:    d.PriceChangePercentage24h,
			High:      d.High24h,
			Low:       d.Low24h,
			Volume:    d.TotalVolume,
			MarketCap: d.MarketCap,
			Timestamp: timestamp,
			Source:    "coingecko",
		})
	}

	return result, nil
}

func fetchKuCoin() ([]MarketData, error) {
	url := "https://api.kucoin.com/api/v1/market/allTickers"
	
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	
	var response struct {
		Data struct {
			Ticker []struct {
				Symbol     string `json:"symbol"`
				Last       string `json:"last"`
				ChangeRate string `json:"changeRate"`
				High       string `json:"high"`
				Low        string `json:"low"`
				VolValue   string `json:"volValue"`
			} `json:"ticker"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &response); err != nil {
		return nil, err
	}

	var result []MarketData
	timestamp := time.Now().Format(time.RFC3339)
	count := 0

	for _, t := range response.Data.Ticker {
		if !strings.HasSuffix(t.Symbol, "-USDT") || count >= 100 {
			continue
		}
		
		price, _ := strconv.ParseFloat(t.Last, 64)
		change, _ := strconv.ParseFloat(t.ChangeRate, 64)
		high, _ := strconv.ParseFloat(t.High, 64)
		low, _ := strconv.ParseFloat(t.Low, 64)
		volume, _ := strconv.ParseFloat(t.VolValue, 64)

		result = append(result, MarketData{
			Symbol:    strings.Replace(t.Symbol, "-", "", 1),
			Price:     price,
			Change:    change * 100,
			High:      high,
			Low:       low,
			Volume:    volume,
			Timestamp: timestamp,
			Source:    "kucoin",
		})
		count++
	}

	return result, nil
}

func fetchBybit() ([]MarketData, error) {
	url := "https://api.bybit.com/v5/market/tickers?category=spot"
	
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	
	var response struct {
		Result struct {
			List []struct {
				Symbol       string `json:"symbol"`
				LastPrice    string `json:"lastPrice"`
				Price24hPcnt string `json:"price24hPcnt"`
				HighPrice24h string `json:"highPrice24h"`
				LowPrice24h  string `json:"lowPrice24h"`
				Turnover24h  string `json:"turnover24h"`
			} `json:"list"`
		} `json:"result"`
	}

	if err := json.Unmarshal(body, &response); err != nil {
		return nil, err
	}

	var result []MarketData
	timestamp := time.Now().Format(time.RFC3339)
	count := 0

	for _, t := range response.Result.List {
		if !strings.HasSuffix(t.Symbol, "USDT") || count >= 100 {
			continue
		}
		
		price, _ := strconv.ParseFloat(t.LastPrice, 64)
		change, _ := strconv.ParseFloat(t.Price24hPcnt, 64)
		high, _ := strconv.ParseFloat(t.HighPrice24h, 64)
		low, _ := strconv.ParseFloat(t.LowPrice24h, 64)
		volume, _ := strconv.ParseFloat(t.Turnover24h, 64)

		result = append(result, MarketData{
			Symbol:    t.Symbol,
			Price:     price,
			Change:    change * 100,
			High:      high,
			Low:       low,
			Volume:    volume,
			Timestamp: timestamp,
			Source:    "bybit",
		})
		count++
	}

	return result, nil
}

func fetchMarketData(source string) ([]MarketData, error) {
	switch source {
	case "coingecko":
		return fetchCoinGecko()
	case "kucoin":
		return fetchKuCoin()
	case "bybit":
		return fetchBybit()
	default:
		return fetchCoinGecko()
	}
}

// ═══════════════════════════════════════════════════════════════
// تشخیص نهنگ و پامپ/دامپ
// ═══════════════════════════════════════════════════════════════

func detectWhales(data []MarketData) []Whale {
	var whales []Whale
	timestamp := time.Now().Format(time.RFC3339)

	for _, m := range data {
		if m.Volume >= config.WhaleThreshold {
			whaleType := "buy"
			if m.Change < 0 {
				whaleType = "sell"
			}

			whale := Whale{
				ID:              time.Now().UnixNano(),
				Symbol:          m.Symbol,
				Price:           m.Price,
				Volume:          m.Volume,
				ChangePercent:   m.Change,
				WhaleType:       whaleType,
				IsReal:          true,
				ConfidenceScore: calculateWhaleConfidence(m),
				Timestamp:       timestamp,
			}

			whales = append(whales, whale)
			saveWhale(whale)
			createSignal(whale)
		}
	}

	return whales
}

func calculateWhaleConfidence(m MarketData) float64 {
	score := 50.0 // پایه

	// حجم بالاتر = امتیاز بیشتر
	if m.Volume >= 1000000 {
		score += 20
	} else if m.Volume >= 500000 {
		score += 10
	}

	// تغییر قیمت معنادار
	if math.Abs(m.Change) >= 5 {
		score += 15
	} else if math.Abs(m.Change) >= 3 {
		score += 10
	}

	// نزدیکی به High یا Low
	if m.Price >= m.High*0.98 || m.Price <= m.Low*1.02 {
		score += 15
	}

	return math.Min(score, 100)
}

func detectPumpDumps(data []MarketData) []PumpDump {
	var pumpDumps []PumpDump
	timestamp := time.Now().Format(time.RFC3339)

	pricesMutex.Lock()
	defer pricesMutex.Unlock()

	for _, m := range data {
		if prev, exists := previousPrices[m.Symbol]; exists {
			change := ((m.Price - prev) / prev) * 100

			if math.Abs(change) >= config.PumpThreshold {
				eventType := "pump"
				if change < 0 {
					eventType = "dump"
				}

				pd := PumpDump{
					ID:            time.Now().UnixNano(),
					Symbol:        m.Symbol,
					Price:         m.Price,
					PrevPrice:     prev,
					ChangePercent: change,
					EventType:     eventType,
					Volume:        m.Volume,
					Timestamp:     timestamp,
				}

				pumpDumps = append(pumpDumps, pd)
				savePumpDump(pd)
			}
		}

		previousPrices[m.Symbol] = m.Price
	}

	return pumpDumps
}

// ═══════════════════════════════════════════════════════════════
// سیگنال‌ها و اعتبارسنجی
// ═══════════════════════════════════════════════════════════════

func createSignal(whale Whale) {
	signalType := "LONG"
	if whale.WhaleType == "sell" {
		signalType = "SHORT"
	}

	// تشخیص ترند و whale flow
	trend := "neutral"
	whaleFlow := "neutral"
	if whale.ChangePercent > 2 {
		trend = "bullish"
		whaleFlow = "inflow"
	} else if whale.ChangePercent < -2 {
		trend = "bearish"
		whaleFlow = "outflow"
	}

	signal := Signal{
		ID:          time.Now().UnixNano(),
		Symbol:      whale.Symbol,
		SignalType:  signalType,
		EntryPrice:  whale.Price,
		Volume:      whale.Volume,
		FinalStatus: "pending",
		Trend:       trend,
		WhaleFlow:   whaleFlow,
		Timestamp:   time.Now().Format(time.RFC3339),
	}

	saveSignal(signal)
}

func validateSignal(signal *Signal, currentPrice float64, stage int) bool {
	priceChange := ((currentPrice - signal.EntryPrice) / signal.EntryPrice) * 100
	minChange := config.MinPriceChange

	isValid := false

	if signal.SignalType == "LONG" {
		if priceChange >= minChange {
			isValid = true
		}
	} else { // SHORT
		if priceChange <= -minChange {
			isValid = true
		}
	}

	switch stage {
	case 1:
		signal.Price1Min = currentPrice
		signal.Change1Min = priceChange
		signal.Valid1Min = isValid
	case 2:
		signal.Price2Min = currentPrice
		signal.Change2Min = priceChange
		signal.Valid2Min = isValid
	case 3:
		signal.Price4Min = currentPrice
		signal.Change4Min = priceChange
		signal.Valid4Min = isValid
	}

	return isValid
}

func calculateSignalScore(signal *Signal) int {
	score := 0
	weights := config.ValidationWeights

	if signal.Valid1Min {
		score += weights[0]
	}
	if signal.Valid2Min {
		score += weights[1]
	}
	if signal.Valid4Min {
		score += weights[2]
	}

	// امتیاز ترند
	if signal.SignalType == "LONG" && signal.Trend == "bullish" {
		score += 10
	} else if signal.SignalType == "SHORT" && signal.Trend == "bearish" {
		score += 10
	}

	// امتیاز whale flow
	if signal.SignalType == "LONG" && signal.WhaleFlow == "inflow" {
		score += 10
	} else if signal.SignalType == "SHORT" && signal.WhaleFlow == "outflow" {
		score += 10
	}

	if score > 100 {
		score = 100
	}

	return score
}

func getFinalStatus(signal *Signal) string {
	validCount := 0
	if signal.Valid1Min {
		validCount++
	}
	if signal.Valid2Min {
		validCount++
	}
	if signal.Valid4Min {
		validCount++
	}

	if validCount >= 2 {
		return "valid"
	}
	return "invalid"
}

func checkPendingSignals(data []MarketData) {
	priceMap := make(map[string]float64)
	for _, m := range data {
		priceMap[m.Symbol] = m.Price
	}

	signals := getPendingSignals()
	now := time.Now()
	validationTimes := config.ValidationTimes

	for _, signal := range signals {
		signalTime, _ := time.Parse(time.RFC3339, signal.Timestamp)
		elapsed := now.Sub(signalTime).Minutes()

		currentPrice, exists := priceMap[signal.Symbol]
		if !exists {
			continue
		}

		updated := false

		// مرحله 1
		if elapsed >= float64(validationTimes[0]) && signal.Price1Min == 0 {
			validateSignal(&signal, currentPrice, 1)
			updated = true
		}

		// مرحله 2
		if elapsed >= float64(validationTimes[1]) && signal.Price2Min == 0 {
			validateSignal(&signal, currentPrice, 2)
			updated = true
		}

		// مرحله 3
		if elapsed >= float64(validationTimes[2]) && signal.Price4Min == 0 {
			validateSignal(&signal, currentPrice, 3)
			signal.FinalStatus = getFinalStatus(&signal)
			signal.Score = calculateSignalScore(&signal)
			signal.ValidatedAt = time.Now().Format(time.RFC3339)
			updated = true
		}

		if updated {
			updateSignal(signal)
		}
	}
}

// ═══════════════════════════════════════════════════════════════
// اتو ترید
// ═══════════════════════════════════════════════════════════════

type AutoTrader struct {
	IsRunning         bool
	DailyTrades       int
	ConsecutiveLosses int
	LastTradeDate     string
	PnL               float64
	TotalCommission   float64
	OpenTrades        map[int64]Trade
	mutex             sync.Mutex
}

var autoTrader = &AutoTrader{
	OpenTrades: make(map[int64]Trade),
}

func (at *AutoTrader) Start() {
	at.mutex.Lock()
	defer at.mutex.Unlock()

	if at.IsRunning {
		return
	}

	at.IsRunning = true
	log.Println("🤖 اتو ترید شروع شد")

	go at.run()
}

func (at *AutoTrader) Stop() {
	at.mutex.Lock()
	defer at.mutex.Unlock()

	at.IsRunning = false
	log.Println("⏹️ اتو ترید متوقف شد")
}

func (at *AutoTrader) run() {
	for at.IsRunning {
		// چک محدودیت‌ها
		if !at.canTrade() {
			time.Sleep(10 * time.Second)
			continue
		}

		// خواندن سیگنال‌های معتبر از دیتابیس
		validSignals := getValidSignalsForTrade(config.MinScoreForTrade)

		if len(validSignals) > 0 {
			// بهترین سیگنال (بالاترین امتیاز)
			bestSignal := validSignals[0]

			// چک که قبلاً ترید نزده باشیم
			if _, exists := at.OpenTrades[bestSignal.ID]; !exists {
				at.executeTrade(bestSignal)
			}
		}

		// چک ترید‌های باز برای TP/SL
		at.checkOpenTrades()

		time.Sleep(10 * time.Second)
	}
}

func (at *AutoTrader) canTrade() bool {
	today := time.Now().Format("2006-01-02")

	if at.LastTradeDate != today {
		at.DailyTrades = 0
		at.LastTradeDate = today
	}

	if at.DailyTrades >= config.MaxDailyTrades {
		log.Println("⚠️ حداکثر ترید روزانه")
		return false
	}

	if at.ConsecutiveLosses >= config.MaxConsecutiveLosses {
		log.Println("⚠️ ضررهای متوالی - توقف")
		at.Stop()
		return false
	}

	return true
}

func (at *AutoTrader) executeTrade(signal Signal) {
	at.mutex.Lock()
	defer at.mutex.Unlock()

	// محاسبه SL و TP
	var stopLoss, takeProfit float64
	if signal.SignalType == "LONG" {
		stopLoss = signal.EntryPrice * (1 - config.StopLoss/100)
		takeProfit = signal.EntryPrice * (1 + config.TakeProfit/100)
	} else {
		stopLoss = signal.EntryPrice * (1 + config.StopLoss/100)
		takeProfit = signal.EntryPrice * (1 - config.TakeProfit/100)
	}

	trade := Trade{
		ID:         time.Now().UnixNano(),
		SignalID:   signal.ID,
		Symbol:     signal.Symbol,
		Side:       signal.SignalType,
		EntryPrice: signal.EntryPrice,
		Amount:     config.TradeAmount,
		Leverage:   config.Leverage,
		StopLoss:   stopLoss,
		TakeProfit: takeProfit,
		Exchange:   config.Exchange,
		Status:     "open",
		OpenedAt:   time.Now().Format(time.RFC3339),
	}

	saveTrade(trade)
	at.OpenTrades[signal.ID] = trade
	at.DailyTrades++

	log.Printf("✅ ترید باز شد: %s %s @ $%.4f", signal.Symbol, signal.SignalType, signal.EntryPrice)

	// ارسال به صرافی
	if config.APIKey != "" && config.SecretKey != "" {
		placeOrder(trade)
	}
}

func (at *AutoTrader) checkOpenTrades() {
	if len(at.OpenTrades) == 0 {
		return
	}

	data, err := fetchMarketData(config.APISource)
	if err != nil {
		return
	}

	priceMap := make(map[string]float64)
	for _, m := range data {
		priceMap[m.Symbol] = m.Price
	}

	for signalID, trade := range at.OpenTrades {
		currentPrice, exists := priceMap[trade.Symbol]
		if !exists {
			continue
		}

		shouldClose := false
		closeReason := ""

		if trade.Side == "LONG" {
			if currentPrice <= trade.StopLoss {
				shouldClose = true
				closeReason = "Stop Loss"
			} else if currentPrice >= trade.TakeProfit {
				shouldClose = true
				closeReason = "Take Profit"
			}
		} else {
			if currentPrice >= trade.StopLoss {
				shouldClose = true
				closeReason = "Stop Loss"
			} else if currentPrice <= trade.TakeProfit {
				shouldClose = true
				closeReason = "Take Profit"
			}
		}

		if shouldClose {
			at.closeTrade(signalID, trade, currentPrice, closeReason)
		}
	}
}

func (at *AutoTrader) closeTrade(signalID int64, trade Trade, exitPrice float64, reason string) {
	at.mutex.Lock()
	defer at.mutex.Unlock()

	// محاسبه PnL
	var pnl float64
	if trade.Side == "LONG" {
		pnl = (exitPrice - trade.EntryPrice) / trade.EntryPrice * trade.Amount * float64(trade.Leverage)
	} else {
		pnl = (trade.EntryPrice - exitPrice) / trade.EntryPrice * trade.Amount * float64(trade.Leverage)
	}

	commission := trade.Amount * config.Commission / 100 * 2
	netPnl := pnl - commission

	trade.ExitPrice = exitPrice
	trade.PnL = pnl
	trade.PnLPercent = (exitPrice - trade.EntryPrice) / trade.EntryPrice * 100
	trade.Commission = commission
	trade.NetPnL = netPnl
	trade.Status = "closed"
	trade.ClosedAt = time.Now().Format(time.RFC3339)

	updateTrade(trade)

	at.PnL += netPnl
	at.TotalCommission += commission

	if netPnl < 0 {
		at.ConsecutiveLosses++
	} else {
		at.ConsecutiveLosses = 0
	}

	delete(at.OpenTrades, signalID)

	emoji := "✅"
	if netPnl < 0 {
		emoji = "❌"
	}
	log.Printf("%s ترید بسته شد: %s %s | PnL: $%.2f", emoji, trade.Symbol, reason, netPnl)
}

// ═══════════════════════════════════════════════════════════════
// API صرافی
// ═══════════════════════════════════════════════════════════════

func signLBank(params map[string]string, secretKey string) string {
	keys := make([]string, 0, len(params))
	for k := range params {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	var parts []string
	for _, k := range keys {
		parts = append(parts, k+"="+params[k])
	}
	queryString := strings.Join(parts, "&")

	h := hmac.New(sha256.New, []byte(secretKey))
	h.Write([]byte(queryString))
	return hex.EncodeToString(h.Sum(nil))
}

func getAccountInfo() AccountInfo {
	if config.APIKey == "" || config.SecretKey == "" {
		return AccountInfo{Success: false, Error: "API Keys not set"}
	}

	// شبیه‌سازی برای تست
	return AccountInfo{
		Success:   true,
		Exchange:  strings.ToUpper(config.Exchange),
		Name:      "User_" + config.APIKey[:8],
		UID:       config.APIKey[:12],
		Balance:   100.0,
		Available: 95.0,
		Locked:    5.0,
	}
}

func placeOrder(trade Trade) {
	log.Printf("📤 ارسال سفارش به %s: %s %s $%.2f", 
		config.Exchange, trade.Symbol, trade.Side, trade.Amount)
	// TODO: پیاده‌سازی واقعی API
}

// ═══════════════════════════════════════════════════════════════
// توابع دیتابیس
// ═══════════════════════════════════════════════════════════════

func saveWhale(whale Whale) {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	_, err := db.Exec(`
		INSERT INTO whales (id, symbol, price, volume, change_percent, whale_type, 
		                    is_real, confidence_score, timestamp, saved_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		whale.ID, whale.Symbol, whale.Price, whale.Volume, whale.ChangePercent,
		whale.WhaleType, whale.IsReal, whale.ConfidenceScore, whale.Timestamp,
		time.Now().Format(time.RFC3339))

	if err != nil {
		log.Printf("خطا در ذخیره نهنگ: %v", err)
	}
}

func saveSignal(signal Signal) {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	_, err := db.Exec(`
		INSERT INTO signals (id, symbol, signal_type, entry_price, volume,
		                     trend, whale_flow, timestamp, saved_at, final_status, score)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0)`,
		signal.ID, signal.Symbol, signal.SignalType, signal.EntryPrice,
		signal.Volume, signal.Trend, signal.WhaleFlow, signal.Timestamp,
		time.Now().Format(time.RFC3339))

	if err != nil {
		log.Printf("خطا در ذخیره سیگنال: %v", err)
	}
}

func updateSignal(signal Signal) {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	_, err := db.Exec(`
		UPDATE signals SET 
			price_1min = ?, price_2min = ?, price_4min = ?,
			change_1min = ?, change_2min = ?, change_4min = ?,
			valid_1min = ?, valid_2min = ?, valid_4min = ?,
			final_status = ?, score = ?, validated_at = ?
		WHERE id = ?`,
		signal.Price1Min, signal.Price2Min, signal.Price4Min,
		signal.Change1Min, signal.Change2Min, signal.Change4Min,
		signal.Valid1Min, signal.Valid2Min, signal.Valid4Min,
		signal.FinalStatus, signal.Score, signal.ValidatedAt, signal.ID)

	if err != nil {
		log.Printf("خطا در بروزرسانی سیگنال: %v", err)
	}
}

func getPendingSignals() []Signal {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	rows, err := db.Query(`
		SELECT id, symbol, signal_type, entry_price, 
		       COALESCE(price_1min, 0), COALESCE(price_2min, 0), COALESCE(price_4min, 0),
		       COALESCE(change_1min, 0), COALESCE(change_2min, 0), COALESCE(change_4min, 0),
		       COALESCE(valid_1min, 0), COALESCE(valid_2min, 0), COALESCE(valid_4min, 0),
		       final_status, score, COALESCE(volume, 0), 
		       COALESCE(trend, ''), COALESCE(whale_flow, ''), timestamp
		FROM signals WHERE final_status = 'pending' ORDER BY timestamp ASC`)
	if err != nil {
		return nil
	}
	defer rows.Close()

	var signals []Signal
	for rows.Next() {
		var s Signal
		err := rows.Scan(&s.ID, &s.Symbol, &s.SignalType, &s.EntryPrice,
			&s.Price1Min, &s.Price2Min, &s.Price4Min,
			&s.Change1Min, &s.Change2Min, &s.Change4Min,
			&s.Valid1Min, &s.Valid2Min, &s.Valid4Min,
			&s.FinalStatus, &s.Score, &s.Volume,
			&s.Trend, &s.WhaleFlow, &s.Timestamp)
		if err != nil {
			continue
		}
		signals = append(signals, s)
	}
	return signals
}

func getValidSignalsForTrade(minScore int) []Signal {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	rows, err := db.Query(`
		SELECT id, symbol, signal_type, entry_price, score, timestamp
		FROM signals 
		WHERE final_status = 'valid' AND score >= ?
		ORDER BY score DESC LIMIT 20`, minScore)
	if err != nil {
		return nil
	}
	defer rows.Close()

	var signals []Signal
	for rows.Next() {
		var s Signal
		rows.Scan(&s.ID, &s.Symbol, &s.SignalType, &s.EntryPrice, &s.Score, &s.Timestamp)
		signals = append(signals, s)
	}
	return signals
}

func getSignals(status string, limit int) []Signal {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	var query string
	var rows *sql.Rows
	var err error

	if status == "all" || status == "" {
		query = `SELECT id, symbol, signal_type, entry_price, 
		         COALESCE(price_1min, 0), COALESCE(price_2min, 0), COALESCE(price_4min, 0),
		         COALESCE(change_1min, 0), COALESCE(change_2min, 0), COALESCE(change_4min, 0),
		         COALESCE(valid_1min, 0), COALESCE(valid_2min, 0), COALESCE(valid_4min, 0),
		         final_status, score, timestamp
		         FROM signals ORDER BY timestamp DESC LIMIT ?`
		rows, err = db.Query(query, limit)
	} else {
		query = `SELECT id, symbol, signal_type, entry_price, 
		         COALESCE(price_1min, 0), COALESCE(price_2min, 0), COALESCE(price_4min, 0),
		         COALESCE(change_1min, 0), COALESCE(change_2min, 0), COALESCE(change_4min, 0),
		         COALESCE(valid_1min, 0), COALESCE(valid_2min, 0), COALESCE(valid_4min, 0),
		         final_status, score, timestamp
		         FROM signals WHERE final_status = ? ORDER BY timestamp DESC LIMIT ?`
		rows, err = db.Query(query, status, limit)
	}

	if err != nil {
		return nil
	}
	defer rows.Close()

	var signals []Signal
	for rows.Next() {
		var s Signal
		rows.Scan(&s.ID, &s.Symbol, &s.SignalType, &s.EntryPrice,
			&s.Price1Min, &s.Price2Min, &s.Price4Min,
			&s.Change1Min, &s.Change2Min, &s.Change4Min,
			&s.Valid1Min, &s.Valid2Min, &s.Valid4Min,
			&s.FinalStatus, &s.Score, &s.Timestamp)
		signals = append(signals, s)
	}
	return signals
}

func getSignalStats() SignalStats {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	var stats SignalStats

	db.QueryRow("SELECT COUNT(*) FROM signals WHERE final_status = 'valid'").Scan(&stats.Valid)
	db.QueryRow("SELECT COUNT(*) FROM signals WHERE final_status = 'invalid'").Scan(&stats.Invalid)
	db.QueryRow("SELECT COUNT(*) FROM signals WHERE final_status = 'pending'").Scan(&stats.Pending)

	total := stats.Valid + stats.Invalid
	if total > 0 {
		stats.Accuracy = float64(stats.Valid) / float64(total) * 100
	}

	return stats
}

func savePumpDump(pd PumpDump) {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	db.Exec(`INSERT INTO pump_dumps (id, symbol, price, prev_price, change_percent, 
	         event_type, volume, timestamp, saved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		pd.ID, pd.Symbol, pd.Price, pd.PrevPrice, pd.ChangePercent,
		pd.EventType, pd.Volume, pd.Timestamp, time.Now().Format(time.RFC3339))
}

func getPumpDumps(limit int) []PumpDump {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	rows, _ := db.Query(`SELECT id, symbol, price, prev_price, change_percent, 
	                     event_type, volume, timestamp FROM pump_dumps 
	                     ORDER BY timestamp DESC LIMIT ?`, limit)
	defer rows.Close()

	var pds []PumpDump
	for rows.Next() {
		var pd PumpDump
		rows.Scan(&pd.ID, &pd.Symbol, &pd.Price, &pd.PrevPrice, &pd.ChangePercent,
			&pd.EventType, &pd.Volume, &pd.Timestamp)
		pds = append(pds, pd)
	}
	return pds
}

func getWhales(limit int) []Whale {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	rows, _ := db.Query(`SELECT id, symbol, price, volume, change_percent, 
	                     whale_type, is_real, confidence_score, timestamp 
	                     FROM whales ORDER BY timestamp DESC LIMIT ?`, limit)
	defer rows.Close()

	var whales []Whale
	for rows.Next() {
		var w Whale
		rows.Scan(&w.ID, &w.Symbol, &w.Price, &w.Volume, &w.ChangePercent,
			&w.WhaleType, &w.IsReal, &w.ConfidenceScore, &w.Timestamp)
		whales = append(whales, w)
	}
	return whales
}

func getWhaleFlow() WhaleFlow {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	var flow WhaleFlow

	since := time.Now().Add(-24 * time.Hour).Format(time.RFC3339)

	db.QueryRow(`SELECT COALESCE(SUM(volume), 0) FROM whales 
	             WHERE whale_type = 'buy' AND timestamp > ?`, since).Scan(&flow.Inflow)
	db.QueryRow(`SELECT COALESCE(SUM(volume), 0) FROM whales 
	             WHERE whale_type = 'sell' AND timestamp > ?`, since).Scan(&flow.Outflow)

	flow.Net = flow.Inflow - flow.Outflow

	return flow
}

func saveTrade(trade Trade) {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	db.Exec(`INSERT INTO trades (id, signal_id, symbol, side, entry_price, amount,
	         leverage, stop_loss, take_profit, exchange, status, opened_at, saved_at)
	         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)`,
		trade.ID, trade.SignalID, trade.Symbol, trade.Side, trade.EntryPrice,
		trade.Amount, trade.Leverage, trade.StopLoss, trade.TakeProfit,
		trade.Exchange, trade.OpenedAt, time.Now().Format(time.RFC3339))
}

func updateTrade(trade Trade) {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	db.Exec(`UPDATE trades SET exit_price = ?, pnl = ?, pnl_percent = ?, 
	         commission = ?, net_pnl = ?, status = 'closed', closed_at = ?
	         WHERE id = ?`,
		trade.ExitPrice, trade.PnL, trade.PnLPercent, trade.Commission,
		trade.NetPnL, trade.ClosedAt, trade.ID)
}

func getTrades(status string, limit int) []Trade {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	var query string
	var rows *sql.Rows

	if status == "" {
		query = `SELECT id, signal_id, symbol, side, entry_price, 
		         COALESCE(exit_price, 0), amount, leverage, 
		         COALESCE(pnl, 0), COALESCE(pnl_percent, 0), 
		         COALESCE(commission, 0), COALESCE(net_pnl, 0),
		         status, stop_loss, take_profit, exchange, opened_at, 
		         COALESCE(closed_at, '') FROM trades ORDER BY opened_at DESC LIMIT ?`
		rows, _ = db.Query(query, limit)
	} else {
		query = `SELECT id, signal_id, symbol, side, entry_price, 
		         COALESCE(exit_price, 0), amount, leverage, 
		         COALESCE(pnl, 0), COALESCE(pnl_percent, 0), 
		         COALESCE(commission, 0), COALESCE(net_pnl, 0),
		         status, stop_loss, take_profit, exchange, opened_at, 
		         COALESCE(closed_at, '') FROM trades WHERE status = ? 
		         ORDER BY opened_at DESC LIMIT ?`
		rows, _ = db.Query(query, status, limit)
	}
	defer rows.Close()

	var trades []Trade
	for rows.Next() {
		var t Trade
		rows.Scan(&t.ID, &t.SignalID, &t.Symbol, &t.Side, &t.EntryPrice,
			&t.ExitPrice, &t.Amount, &t.Leverage, &t.PnL, &t.PnLPercent,
			&t.Commission, &t.NetPnL, &t.Status, &t.StopLoss, &t.TakeProfit,
			&t.Exchange, &t.OpenedAt, &t.ClosedAt)
		trades = append(trades, t)
	}
	return trades
}

func getTradeStats(period string) TradeStats {
	dbMutex.Lock()
	defer dbMutex.Unlock()

	var since string
	if period == "daily" {
		since = time.Now().Format("2006-01-02")
	} else {
		since = time.Now().Format("2006-01") + "-01"
	}

	var stats TradeStats

	row := db.QueryRow(`
		SELECT COUNT(*), 
		       COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0),
		       COALESCE(SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END), 0),
		       COALESCE(SUM(net_pnl), 0),
		       COALESCE(SUM(commission), 0)
		FROM trades WHERE status = 'closed' AND DATE(opened_at) >= ?`, since)

	row.Scan(&stats.TotalTrades, &stats.Wins, &stats.Losses,
		&stats.TotalPnL, &stats.TotalCommission)

	if stats.TotalTrades > 0 {
		stats.WinRate = float64(stats.Wins) / float64(stats.TotalTrades) * 100
	}

	return stats
}

// ═══════════════════════════════════════════════════════════════
// HTTP Handlers
// ═══════════════════════════════════════════════════════════════

func handleConfig(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	if r.Method == "POST" {
		json.NewDecoder(r.Body).Decode(&config)
		json.NewEncoder(w).Encode(map[string]interface{}{"success": true, "config": config})
		return
	}

	json.NewEncoder(w).Encode(config)
}

func handleMarket(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	source := r.URL.Query().Get("source")
	if source == "" {
		source = config.APISource
	}

	data, err := fetchMarketData(source)
	if err != nil {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": false,
			"error":   err.Error(),
			"source":  source,
		})
		return
	}

	// تشخیص نهنگ و پامپ/دامپ
	whales := detectWhales(data)
	pumpDumps := detectPumpDumps(data)

	// چک سیگنال‌های در انتظار
	checkPendingSignals(data)

	json.NewEncoder(w).Encode(map[string]interface{}{
		"success":    true,
		"data":       data,
		"source":     source,
		"whales":     whales,
		"pump_dumps": pumpDumps,
	})
}

func handleSignals(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	status := r.URL.Query().Get("status")
	signals := getSignals(status, 100)
	stats := getSignalStats()

	json.NewEncoder(w).Encode(map[string]interface{}{
		"signals": signals,
		"stats":   stats,
	})
}

func handleWhales(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	whales := getWhales(100)
	flow := getWhaleFlow()

	json.NewEncoder(w).Encode(map[string]interface{}{
		"whales": whales,
		"flow":   flow,
	})
}

func handlePumpDumps(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	json.NewEncoder(w).Encode(getPumpDumps(50))
}

func handleAccount(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	json.NewEncoder(w).Encode(getAccountInfo())
}

func handleTradeQueue(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	json.NewEncoder(w).Encode(getValidSignalsForTrade(config.MinScoreForTrade))
}

func handleAutoTradeStart(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	autoTrader.Start()
	json.NewEncoder(w).Encode(map[string]interface{}{"success": true, "message": "اتو ترید شروع شد"})
}

func handleAutoTradeStop(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	autoTrader.Stop()
	json.NewEncoder(w).Encode(map[string]interface{}{"success": true, "message": "اتو ترید متوقف شد"})
}

func handleAutoTradeStats(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	json.NewEncoder(w).Encode(map[string]interface{}{
		"is_running":          autoTrader.IsRunning,
		"daily_trades":        autoTrader.DailyTrades,
		"consecutive_losses":  autoTrader.ConsecutiveLosses,
		"pnl":                 autoTrader.PnL,
		"commission":          autoTrader.TotalCommission,
		"net_pnl":             autoTrader.PnL - autoTrader.TotalCommission,
		"open_trades":         len(autoTrader.OpenTrades),
	})
}

func handleTrades(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	status := r.URL.Query().Get("status")
	trades := getTrades(status, 100)
	dailyStats := getTradeStats("daily")
	monthlyStats := getTradeStats("monthly")

	json.NewEncoder(w).Encode(map[string]interface{}{
		"trades":        trades,
		"daily_stats":   dailyStats,
		"monthly_stats": monthlyStats,
	})
}

func handleExport(w http.ResponseWriter, r *http.Request) {
	table := r.URL.Query().Get("table")
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=%s.csv", table))

	// TODO: Export CSV
	fmt.Fprintf(w, "id,symbol,timestamp\n")
}

// ═══════════════════════════════════════════════════════════════
// HTML Template
// ═══════════════════════════════════════════════════════════════

var htmlTemplate = `
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🐋 Whale Hunter Pro v5.0 - Go Edition</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * { font-family: 'Vazirmatn', sans-serif; }
        .glass { background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(10px); }
        .live-dot { animation: pulse 1s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        .scrollbar-thin::-webkit-scrollbar { width: 4px; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background: #475569; border-radius: 2px; }
    </style>
</head>
<body class="bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white min-h-screen">
    
    <header class="glass border-b border-slate-700 sticky top-0 z-50">
        <div class="container mx-auto px-4 py-3">
            <div class="flex items-center justify-between flex-wrap gap-3">
                <div class="flex items-center gap-4">
                    <h1 class="text-2xl font-bold flex items-center gap-2">
                        <span class="text-4xl">🐋</span>
                        <span class="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                            Whale Hunter Pro v5.0
                        </span>
                        <span class="text-xs bg-green-500/20 text-green-400 px-2 py-1 rounded-full">Go Edition 🚀</span>
                    </h1>
                    <div id="apiStatus" class="flex items-center gap-2 px-3 py-1 rounded-full bg-yellow-500/20 text-yellow-400 text-sm">
                        <span class="w-2 h-2 rounded-full bg-yellow-500 live-dot"></span>
                        <span>در حال اتصال...</span>
                    </div>
                </div>
                <div class="flex items-center gap-3">
                    <select id="apiSource" onchange="changeApi()" class="bg-slate-800 rounded-lg px-3 py-1 border border-slate-600 text-sm">
                        <option value="coingecko">🦎 CoinGecko</option>
                        <option value="kucoin">🟢 KuCoin</option>
                        <option value="bybit">🟡 Bybit</option>
                    </select>
                    <span id="lastUpdate" class="text-xs text-slate-400">-</span>
                </div>
            </div>
            <nav class="flex gap-2 mt-3 flex-wrap">
                <button onclick="showTab('dashboard')" class="tab-btn px-4 py-2 rounded-lg bg-slate-700 text-sm" data-tab="dashboard">🎯 داشبورد</button>
                <button onclick="showTab('market')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700 text-sm" data-tab="market">📊 بازار</button>
                <button onclick="showTab('whales')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700 text-sm" data-tab="whales">🐋 نهنگ‌ها</button>
                <button onclick="showTab('signals')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700 text-sm" data-tab="signals">📡 سیگنال‌ها</button>
                <button onclick="showTab('autotrade')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700 text-sm" data-tab="autotrade">🤖 اتو ترید</button>
                <button onclick="showTab('settings')" class="tab-btn px-4 py-2 rounded-lg hover:bg-slate-700 text-sm" data-tab="settings">⚙️ تنظیمات</button>
            </nav>
        </div>
    </header>

    <main class="container mx-auto px-4 py-6">
        
        <!-- Dashboard -->
        <div id="dashboard-tab" class="tab-content">
            <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <div class="text-slate-400 text-xs">نهنگ مادر</div>
                    <div class="text-2xl font-bold text-blue-400" id="statWhales">0</div>
                </div>
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <div class="text-slate-400 text-xs">سیگنال معتبر</div>
                    <div class="text-2xl font-bold text-green-400" id="statValid">0</div>
                </div>
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <div class="text-slate-400 text-xs">در انتظار</div>
                    <div class="text-2xl font-bold text-yellow-400" id="statPending">0</div>
                </div>
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <div class="text-slate-400 text-xs">دقت سیگنال</div>
                    <div class="text-2xl font-bold text-purple-400" id="statAccuracy">0%</div>
                </div>
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <div class="text-slate-400 text-xs">پامپ/دامپ</div>
                    <div class="text-2xl font-bold text-orange-400" id="statPumpDump">0</div>
                </div>
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <div class="text-slate-400 text-xs">Whale Flow</div>
                    <div class="text-2xl font-bold text-cyan-400" id="statFlow">$0</div>
                </div>
            </div>
            
            <div class="mb-6 glass rounded-xl p-4 border border-purple-500/30">
                <h3 class="font-bold text-purple-400 mb-2">🧮 فرمول اعتبارسنجی (1، 2، 4 دقیقه)</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div class="p-3 bg-slate-800 rounded-lg">
                        <div class="text-green-400 font-bold mb-1">✅ معتبر:</div>
                        <ul class="text-slate-300 text-xs space-y-1">
                            <li>• LONG + قیمت بالا رفت (≥0.1%)</li>
                            <li>• SHORT + قیمت پایین آمد</li>
                        </ul>
                    </div>
                    <div class="p-3 bg-slate-800 rounded-lg">
                        <div class="text-red-400 font-bold mb-1">❌ نامعتبر:</div>
                        <ul class="text-slate-300 text-xs space-y-1">
                            <li>• مخالف پیش‌بینی</li>
                            <li>• تغییر کمتر از حداقل</li>
                        </ul>
                    </div>
                </div>
            </div>
            
            <div class="mb-6 glass rounded-xl p-4 border border-orange-500/30">
                <h3 class="font-bold text-orange-400 mb-3">🚨 هشدار پامپ/دامپ</h3>
                <div id="pumpDumpList" class="flex gap-3 overflow-x-auto pb-2">
                    <div class="text-slate-400 text-sm">در انتظار...</div>
                </div>
            </div>
            
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <h3 class="font-bold mb-3 flex items-center gap-2">
                        🐋 نهنگ‌های اخیر
                        <span class="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full live-dot">LIVE</span>
                    </h3>
                    <div id="whaleList" class="space-y-2 max-h-64 overflow-y-auto scrollbar-thin">
                        <div class="text-slate-400 text-sm">در انتظار...</div>
                    </div>
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
                        <div class="pt-3 border-t border-slate-600 flex justify-between">
                            <span>خالص</span>
                            <span id="flowNet" class="font-bold text-lg">$0</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Market Tab -->
        <div id="market-tab" class="tab-content hidden">
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="flex justify-between items-center mb-4 flex-wrap gap-3">
                    <h3 class="font-bold">📊 بازار (هر 10 ثانیه)</h3>
                    <div class="flex gap-2">
                        <input type="text" id="searchMarket" placeholder="🔍 جستجو..." 
                            class="bg-slate-800 rounded-lg px-3 py-1 border border-slate-600 text-sm w-32"
                            onkeyup="filterMarket()">
                        <select id="filterMarket" class="bg-slate-800 rounded-lg px-3 py-1 border border-slate-600 text-sm" onchange="filterMarket()">
                            <option value="all">همه</option>
                            <option value="pump">🟢 پامپ</option>
                            <option value="dump">🔴 دامپ</option>
                            <option value="whale">🐋 نهنگ</option>
                        </select>
                    </div>
                </div>
                <div class="overflow-x-auto max-h-[500px] overflow-y-auto">
                    <table class="w-full text-sm">
                        <thead class="bg-slate-800 sticky top-0">
                            <tr class="text-slate-400">
                                <th class="text-right py-2 px-2 cursor-pointer" onclick="sortMarket('symbol')">نماد</th>
                                <th class="text-right py-2 px-2 cursor-pointer" onclick="sortMarket('price')">قیمت</th>
                                <th class="text-right py-2 px-2 cursor-pointer" onclick="sortMarket('change')">تغییر</th>
                                <th class="text-right py-2 px-2 cursor-pointer" onclick="sortMarket('volume')">حجم</th>
                                <th class="text-right py-2 px-2">وضعیت</th>
                            </tr>
                        </thead>
                        <tbody id="marketTable">
                            <tr><td colspan="5" class="text-center py-8 text-slate-400">در حال بارگذاری...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Whales Tab -->
        <div id="whales-tab" class="tab-content hidden">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <h3 class="font-bold mb-3">⚙️ تنظیمات رصد</h3>
                    <div class="space-y-3">
                        <div>
                            <label class="text-slate-400 text-xs">آستانه نهنگ ($)</label>
                            <input type="number" id="whaleThreshold" value="500000" 
                                class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        </div>
                        <div>
                            <label class="text-slate-400 text-xs">آستانه پامپ/دامپ (%)</label>
                            <input type="number" id="pumpThreshold" value="3" step="0.5"
                                class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        </div>
                        <button onclick="saveWhaleSettings()" class="w-full bg-blue-600 py-2 rounded-lg">💾 ذخیره</button>
                    </div>
                </div>
                <div class="lg:col-span-2 glass rounded-xl p-4 border border-slate-700">
                    <h3 class="font-bold mb-3">🐋 نهنگ‌های شناسایی شده</h3>
                    <div id="whaleFullList" class="space-y-2 max-h-[400px] overflow-y-auto scrollbar-thin">
                        <div class="text-slate-400 text-sm">در انتظار...</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Signals Tab -->
        <div id="signals-tab" class="tab-content hidden">
            <div class="glass rounded-xl p-4 border border-slate-700">
                <div class="flex justify-between items-center mb-4 flex-wrap gap-3">
                    <h3 class="font-bold">📡 سیگنال‌ها (اعتبارسنجی 1، 2، 4 دقیقه)</h3>
                    <div class="flex gap-2">
                        <button onclick="filterSignals('all')" class="px-3 py-1 rounded bg-slate-700 text-sm">همه</button>
                        <button onclick="filterSignals('valid')" class="px-3 py-1 rounded bg-green-500/20 text-green-400 text-sm">✅ معتبر</button>
                        <button onclick="filterSignals('invalid')" class="px-3 py-1 rounded bg-red-500/20 text-red-400 text-sm">❌ نامعتبر</button>
                        <button onclick="filterSignals('pending')" class="px-3 py-1 rounded bg-yellow-500/20 text-yellow-400 text-sm">⏳ انتظار</button>
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
                                <th class="text-right py-2 px-2">امتیاز</th>
                                <th class="text-right py-2 px-2">وضعیت</th>
                            </tr>
                        </thead>
                        <tbody id="signalTable">
                            <tr><td colspan="9" class="text-center py-8 text-slate-400">سیگنالی ثبت نشده</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Auto Trade Tab -->
        <div id="autotrade-tab" class="tab-content hidden">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <h3 class="font-bold mb-3">🔗 اتصال صرافی</h3>
                    <div class="space-y-3">
                        <select id="exchange" class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                            <option value="lbank">LBank</option>
                            <option value="bitunix">Bitunix</option>
                        </select>
                        <input type="text" id="apiKey" placeholder="API Key" 
                            class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600 font-mono text-xs">
                        <input type="password" id="secretKey" placeholder="Secret Key" 
                            class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600 font-mono text-xs">
                        <button onclick="testConnection()" class="w-full bg-purple-600 py-2 rounded-lg">🔌 تست اتصال</button>
                        
                        <div id="accountInfo" class="hidden p-3 bg-green-500/10 rounded-lg border border-green-500/30">
                            <div class="text-green-400 font-bold mb-2">👤 اطلاعات حساب</div>
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
                                    <span id="accBalance" class="text-green-400 font-bold">$0</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <h3 class="font-bold mb-3">⚙️ تنظیمات معامله</h3>
                    <div class="space-y-3">
                        <div>
                            <label class="text-slate-400 text-xs">مبلغ (USDT)</label>
                            <input type="number" id="tradeAmount" value="5" min="5" 
                                class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                        </div>
                        <div>
                            <label class="text-slate-400 text-xs">اهرم</label>
                            <select id="leverage" class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                                <option value="3">3x</option>
                                <option value="5" selected>5x</option>
                                <option value="10">10x</option>
                                <option value="20">20x</option>
                            </select>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="text-slate-400 text-xs">حد ضرر (%)</label>
                                <input type="number" id="stopLoss" value="2" step="0.5"
                                    class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                            </div>
                            <div>
                                <label class="text-slate-400 text-xs">حد سود (%)</label>
                                <input type="number" id="takeProfit" value="4" step="0.5"
                                    class="w-full bg-slate-800 rounded-lg px-3 py-2 border border-slate-600">
                            </div>
                        </div>
                        <div class="p-2 bg-orange-500/10 rounded-lg border border-orange-500/30">
                            <div class="text-orange-400 text-xs font-bold mb-1">🛡️ محدودیت‌ها</div>
                            <div class="grid grid-cols-2 gap-2">
                                <div>
                                    <label class="text-slate-400 text-xs">حداکثر ترید روزانه</label>
                                    <input type="number" id="maxDaily" value="4" min="1" max="20"
                                        class="w-full bg-slate-700 rounded px-2 py-1 border border-slate-600 text-sm">
                                </div>
                                <div>
                                    <label class="text-slate-400 text-xs">حداکثر ضرر متوالی</label>
                                    <input type="number" id="maxLosses" value="4" min="1" max="10"
                                        class="w-full bg-slate-700 rounded px-2 py-1 border border-slate-600 text-sm">
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="glass rounded-xl p-4 border border-slate-700">
                    <h3 class="font-bold mb-3">🤖 کنترل</h3>
                    <div class="space-y-3">
                        <div class="p-4 bg-slate-800 rounded-lg text-center">
                            <div class="text-sm text-slate-400">وضعیت</div>
                            <div id="tradeStatus" class="text-xl font-bold text-slate-400">غیرفعال</div>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div class="p-2 bg-slate-800 rounded-lg text-center">
                                <div class="text-lg font-bold text-blue-400" id="dailyTrades">0</div>
                                <div class="text-xs text-slate-400">ترید امروز</div>
                            </div>
                            <div class="p-2 bg-slate-800 rounded-lg text-center">
                                <div class="text-lg font-bold text-orange-400" id="consecutiveLosses">0</div>
                                <div class="text-xs text-slate-400">ضرر متوالی</div>
                            </div>
                        </div>
                        <div class="p-2 bg-slate-800 rounded-lg">
                            <div class="flex justify-between text-sm">
                                <span>سود/زیان:</span>
                                <span id="tradePnl" class="font-bold text-green-400">$0</span>
                            </div>
                        </div>
                        <button onclick="startAutoTrade()" id="btnStart" class="w-full bg-green-600 py-3 rounded-lg font-bold">▶️ شروع اتو ترید</button>
                        <button onclick="stopAutoTrade()" id="btnStop" class="hidden w-full bg-red-600 py-3 rounded-lg font-bold">⏹️ توقف</button>
                    </div>
                </div>
            </div>
            
            <div class="mt-6 glass rounded-xl p-4 border border-green-500/30">
                <h3 class="font-bold text-green-400 mb-3">🎯 صف اتو ترید (مرتب بر اساس امتیاز)</h3>
                <div id="tradeQueue" class="space-y-2 max-h-48 overflow-y-auto">
                    <div class="text-slate-400 text-sm">سیگنال معتبری وجود ندارد</div>
                </div>
            </div>
        </div>
        
        <!-- Settings Tab -->
        <div id="settings-tab" class="tab-content hidden">
            <div class="glass rounded-xl p-6 border border-slate-700">
                <h3 class="font-bold text-xl mb-6">⚙️ تنظیمات پارامتریک</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="p-4 bg-slate-800 rounded-xl">
                        <h4 class="font-bold text-purple-400 mb-4">🧮 اعتبارسنجی</h4>
                        <div class="space-y-3">
                            <div>
                                <label class="text-slate-400 text-sm">حداقل تغییر قیمت (%)</label>
                                <input type="number" id="cfgMinChange" value="0.1" step="0.05"
                                    class="w-full bg-slate-700 rounded-lg px-3 py-2 border border-slate-600">
                            </div>
                            <div class="grid grid-cols-3 gap-2">
                                <div>
                                    <label class="text-slate-400 text-xs">زمان 1 (دقیقه)</label>
                                    <input type="number" id="cfgTime1" value="1" min="1"
                                        class="w-full bg-slate-700 rounded-lg px-3 py-2 border border-slate-600">
                                </div>
                                <div>
                                    <label class="text-slate-400 text-xs">زمان 2</label>
                                    <input type="number" id="cfgTime2" value="2" min="1"
                                        class="w-full bg-slate-700 rounded-lg px-3 py-2 border border-slate-600">
                                </div>
                                <div>
                                    <label class="text-slate-400 text-xs">زمان 3</label>
                                    <input type="number" id="cfgTime3" value="4" min="1"
                                        class="w-full bg-slate-700 rounded-lg px-3 py-2 border border-slate-600">
                                </div>
                            </div>
                            <div class="grid grid-cols-3 gap-2">
                                <div>
                                    <label class="text-slate-400 text-xs">وزن 1 (%)</label>
                                    <input type="number" id="cfgWeight1" value="20"
                                        class="w-full bg-slate-700 rounded-lg px-3 py-2 border border-slate-600">
                                </div>
                                <div>
                                    <label class="text-slate-400 text-xs">وزن 2</label>
                                    <input type="number" id="cfgWeight2" value="30"
                                        class="w-full bg-slate-700 rounded-lg px-3 py-2 border border-slate-600">
                                </div>
                                <div>
                                    <label class="text-slate-400 text-xs">وزن 3</label>
                                    <input type="number" id="cfgWeight3" value="50"
                                        class="w-full bg-slate-700 rounded-lg px-3 py-2 border border-slate-600">
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="p-4 bg-slate-800 rounded-xl">
                        <h4 class="font-bold text-cyan-400 mb-4">📊 اندیکاتورها</h4>
                        <div class="space-y-3">
                            <div class="flex items-center gap-2">
                                <input type="checkbox" id="cfgUseRsi" checked>
                                <label class="text-sm">RSI</label>
                                <input type="number" id="cfgRsiPeriod" value="14" 
                                    class="w-16 bg-slate-700 rounded px-2 py-1 border border-slate-600 text-sm">
                            </div>
                            <div class="flex items-center gap-2">
                                <input type="checkbox" id="cfgUseMacd" checked>
                                <label class="text-sm">MACD</label>
                            </div>
                            <div class="flex items-center gap-2">
                                <input type="checkbox" id="cfgUseVol" checked>
                                <label class="text-sm">Volume</label>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="mt-6 flex gap-4">
                    <button onclick="saveAllSettings()" class="bg-green-600 px-6 py-2 rounded-lg font-bold">💾 ذخیره همه</button>
                    <button onclick="resetSettings()" class="bg-slate-600 px-6 py-2 rounded-lg">🔄 پیش‌فرض</button>
                </div>
            </div>
        </div>
    </main>

    <div id="toast" class="fixed bottom-4 right-4 bg-slate-800 border border-slate-600 rounded-xl p-4 shadow-2xl transform translate-y-20 opacity-0 transition-all z-50 max-w-sm">
        <div class="flex items-center gap-3">
            <span id="toastIcon" class="text-2xl">✅</span>
            <div>
                <div id="toastTitle" class="font-bold"></div>
                <div id="toastMessage" class="text-sm text-slate-400"></div>
            </div>
        </div>
    </div>

    <script>
        let marketData = [];
        let signalFilter = 'all';
        let sortCol = 'volume';
        let sortDir = 'desc';
        
        document.addEventListener('DOMContentLoaded', () => {
            loadConfig();
            fetchData();
            setInterval(fetchData, 10000);
        });
        
        async function fetchData() {
            try {
                const source = document.getElementById('apiSource').value;
                const res = await fetch('/api/market?source=' + source);
                const data = await res.json();
                
                if (data.success) {
                    marketData = data.data;
                    updateApiStatus(true, data.source);
                    updateMarketTable();
                    updateDashboard(data);
                } else {
                    updateApiStatus(false, data.source);
                }
                
                document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('fa-IR');
                
                loadSignals();
                loadWhales();
                loadPumpDumps();
                loadTradeQueue();
                loadTradeStats();
            } catch (e) {
                console.error(e);
                updateApiStatus(false, '');
            }
        }
        
        async function loadConfig() {
            const res = await fetch('/api/config');
            const cfg = await res.json();
            document.getElementById('apiSource').value = cfg.api_source || 'coingecko';
        }
        
        async function loadSignals() {
            const res = await fetch('/api/signals?status=' + signalFilter);
            const data = await res.json();
            updateSignalTable(data.signals);
            document.getElementById('statValid').textContent = data.stats.valid;
            document.getElementById('statPending').textContent = data.stats.pending;
            document.getElementById('statAccuracy').textContent = data.stats.accuracy.toFixed(1) + '%';
        }
        
        async function loadWhales() {
            const res = await fetch('/api/whales');
            const data = await res.json();
            updateWhaleList(data.whales);
            updateWhaleFlow(data.flow);
            document.getElementById('statWhales').textContent = data.whales ? data.whales.length : 0;
        }
        
        async function loadPumpDumps() {
            const res = await fetch('/api/pump-dumps');
            const data = await res.json();
            updatePumpDumpList(data);
            document.getElementById('statPumpDump').textContent = data ? data.length : 0;
        }
        
        async function loadTradeQueue() {
            const res = await fetch('/api/trade-queue');
            const data = await res.json();
            updateTradeQueue(data);
        }
        
        async function loadTradeStats() {
            const res = await fetch('/api/auto-trade/stats');
            const s = await res.json();
            document.getElementById('dailyTrades').textContent = s.daily_trades;
            document.getElementById('consecutiveLosses').textContent = s.consecutive_losses;
            document.getElementById('tradePnl').textContent = '$' + s.net_pnl.toFixed(2);
            document.getElementById('tradeStatus').textContent = s.is_running ? 'فعال' : 'غیرفعال';
            document.getElementById('tradeStatus').className = 'text-xl font-bold ' + (s.is_running ? 'text-green-400' : 'text-slate-400');
            
            if (s.is_running) {
                document.getElementById('btnStart').classList.add('hidden');
                document.getElementById('btnStop').classList.remove('hidden');
            } else {
                document.getElementById('btnStart').classList.remove('hidden');
                document.getElementById('btnStop').classList.add('hidden');
            }
        }
        
        async function testConnection() {
            const exchange = document.getElementById('exchange').value;
            const apiKey = document.getElementById('apiKey').value;
            const secretKey = document.getElementById('secretKey').value;
            
            if (!apiKey || !secretKey) {
                showToast('❌', 'کلیدها را وارد کنید');
                return;
            }
            
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({exchange: exchange, api_key: apiKey, secret_key: secretKey})
            });
            
            const res = await fetch('/api/account');
            const data = await res.json();
            
            if (data.success) {
                document.getElementById('accountInfo').classList.remove('hidden');
                document.getElementById('accExchange').textContent = data.exchange;
                document.getElementById('accName').textContent = data.name;
                document.getElementById('accUid').textContent = data.uid;
                document.getElementById('accBalance').textContent = '$' + data.balance.toFixed(2);
                showToast('✅', 'اتصال برقرار شد');
            } else {
                showToast('❌', data.error || 'خطا');
            }
        }
        
        async function startAutoTrade() {
            await fetch('/api/auto-trade/start', {method: 'POST'});
            showToast('🤖', 'اتو ترید شروع شد');
            loadTradeStats();
        }
        
        async function stopAutoTrade() {
            await fetch('/api/auto-trade/stop', {method: 'POST'});
            showToast('⏹️', 'اتو ترید متوقف شد');
            loadTradeStats();
        }
        
        async function changeApi() {
            const source = document.getElementById('apiSource').value;
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({api_source: source})
            });
            fetchData();
        }
        
        function updateApiStatus(ok, source) {
            const el = document.getElementById('apiStatus');
            if (ok) {
                el.className = 'flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/20 text-green-400 text-sm';
                el.innerHTML = '<span class="w-2 h-2 rounded-full bg-green-500"></span><span>متصل به ' + source + '</span>';
            } else {
                el.className = 'flex items-center gap-2 px-3 py-1 rounded-full bg-red-500/20 text-red-400 text-sm';
                el.innerHTML = '<span class="w-2 h-2 rounded-full bg-red-500"></span><span>خطا</span>';
            }
        }
        
        function updateDashboard(data) {
            // Stats updated from other loaders
        }
        
        function updateMarketTable() {
            const tbody = document.getElementById('marketTable');
            if (!marketData || marketData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-slate-400">در حال بارگذاری...</td></tr>';
                return;
            }
            
            tbody.innerHTML = marketData.slice(0, 100).map(m => {
                const isPump = m.change > 5;
                const isDump = m.change < -5;
                const isWhale = m.volume > 500000;
                return '<tr class="border-b border-slate-700/50 hover:bg-slate-800/50">' +
                    '<td class="py-2 px-2 font-bold">' + m.symbol.replace('USDT', '') + '</td>' +
                    '<td class="py-2 px-2 font-mono">$' + formatPrice(m.price) + '</td>' +
                    '<td class="py-2 px-2 ' + (m.change >= 0 ? 'text-green-400' : 'text-red-400') + '">' + 
                        (m.change >= 0 ? '+' : '') + m.change.toFixed(2) + '%</td>' +
                    '<td class="py-2 px-2 text-blue-400">$' + formatNum(m.volume) + '</td>' +
                    '<td class="py-2 px-2">' + 
                        (isPump ? '<span class="px-2 py-0.5 rounded text-xs bg-green-500/20 text-green-400">پامپ</span>' : 
                         isDump ? '<span class="px-2 py-0.5 rounded text-xs bg-red-500/20 text-red-400">دامپ</span>' : 
                         isWhale ? '<span class="px-2 py-0.5 rounded text-xs bg-blue-500/20 text-blue-400">🐋</span>' : '') +
                    '</td></tr>';
            }).join('');
        }
        
        function updateSignalTable(signals) {
            const tbody = document.getElementById('signalTable');
            if (!signals || signals.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" class="text-center py-8 text-slate-400">سیگنالی ثبت نشده</td></tr>';
                return;
            }
            
            tbody.innerHTML = signals.map(s => {
                return '<tr class="border-b border-slate-700/50 ' + 
                    (s.final_status === 'valid' ? 'border-r-4 border-r-green-500' : 
                     s.final_status === 'invalid' ? 'border-r-4 border-r-red-500' : 'border-r-4 border-r-yellow-500') + '">' +
                    '<td class="py-2 px-2 text-xs">' + formatTime(s.timestamp) + '</td>' +
                    '<td class="py-2 px-2 font-bold">' + s.symbol.replace('USDT', '') + '</td>' +
                    '<td class="py-2 px-2"><span class="px-2 py-0.5 rounded text-xs ' + 
                        (s.signal_type === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400') + '">' + 
                        s.signal_type + '</span></td>' +
                    '<td class="py-2 px-2 font-mono">$' + formatPrice(s.entry_price) + '</td>' +
                    '<td class="py-2 px-2 ' + (s.valid_1min ? 'text-green-400' : s.price_1min ? 'text-red-400' : 'text-slate-400') + '">' + 
                        (s.price_1min ? '$' + formatPrice(s.price_1min) : '⏳') + '</td>' +
                    '<td class="py-2 px-2 ' + (s.valid_2min ? 'text-green-400' : s.price_2min ? 'text-red-400' : 'text-slate-400') + '">' + 
                        (s.price_2min ? '$' + formatPrice(s.price_2min) : '⏳') + '</td>' +
                    '<td class="py-2 px-2 ' + (s.valid_4min ? 'text-green-400' : s.price_4min ? 'text-red-400' : 'text-slate-400') + '">' + 
                        (s.price_4min ? '$' + formatPrice(s.price_4min) : '⏳') + '</td>' +
                    '<td class="py-2 px-2 font-bold">' + s.score + '</td>' +
                    '<td class="py-2 px-2">' + 
                        (s.final_status === 'valid' ? '✅' : s.final_status === 'invalid' ? '❌' : '⏳') + '</td>' +
                '</tr>';
            }).join('');
        }
        
        function updateWhaleList(whales) {
            const container = document.getElementById('whaleList');
            const fullContainer = document.getElementById('whaleFullList');
            
            if (!whales || whales.length === 0) {
                container.innerHTML = '<div class="text-slate-400 text-sm">در انتظار...</div>';
                fullContainer.innerHTML = '<div class="text-slate-400 text-sm">در انتظار...</div>';
                return;
            }
            
            const html = whales.slice(0, 10).map(w => 
                '<div class="p-2 rounded-lg border ' + 
                (w.whale_type === 'buy' ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5') + '">' +
                    '<div class="flex justify-between items-center">' +
                        '<div class="flex items-center gap-2">' +
                            '<span>' + (w.whale_type === 'buy' ? '📥' : '📤') + '</span>' +
                            '<span class="font-bold">' + w.symbol.replace('USDT', '') + '</span>' +
                        '</div>' +
                        '<div class="text-left">' +
                            '<div class="font-bold ' + (w.whale_type === 'buy' ? 'text-green-400' : 'text-red-400') + '">$' + formatNum(w.volume) + '</div>' +
                            '<div class="text-xs text-slate-400">' + formatTime(w.timestamp) + '</div>' +
                        '</div>' +
                    '</div>' +
                '</div>'
            ).join('');
            
            container.innerHTML = html;
            fullContainer.innerHTML = html;
        }
        
        function updateWhaleFlow(flow) {
            if (!flow) return;
            
            const total = flow.inflow + flow.outflow || 1;
            document.getElementById('flowIn').textContent = '$' + formatNum(flow.inflow);
            document.getElementById('flowOut').textContent = '$' + formatNum(flow.outflow);
            document.getElementById('flowInBar').style.width = (flow.inflow / total * 100) + '%';
            document.getElementById('flowOutBar').style.width = (flow.outflow / total * 100) + '%';
            document.getElementById('flowNet').textContent = (flow.net >= 0 ? '+' : '') + '$' + formatNum(Math.abs(flow.net));
            document.getElementById('flowNet').className = 'font-bold text-lg ' + (flow.net >= 0 ? 'text-green-400' : 'text-red-400');
            document.getElementById('statFlow').textContent = '$' + formatNum(flow.net);
        }
        
        function updatePumpDumpList(data) {
            const container = document.getElementById('pumpDumpList');
            if (!data || data.length === 0) {
                container.innerHTML = '<div class="text-slate-400 text-sm">در انتظار...</div>';
                return;
            }
            
            container.innerHTML = data.slice(0, 10).map(p => 
                '<div class="flex-shrink-0 p-2 rounded-lg border min-w-[120px] ' + 
                (p.event_type === 'pump' ? 'border-green-500/30 bg-green-500/10' : 'border-red-500/30 bg-red-500/10') + '">' +
                    '<div class="flex items-center gap-1">' +
                        '<span>' + (p.event_type === 'pump' ? '🚀' : '💥') + '</span>' +
                        '<span class="font-bold text-sm">' + p.symbol.replace('USDT', '') + '</span>' +
                    '</div>' +
                    '<div class="font-bold ' + (p.event_type === 'pump' ? 'text-green-400' : 'text-red-400') + '">' + 
                        (p.change_percent > 0 ? '+' : '') + p.change_percent.toFixed(2) + '%</div>' +
                '</div>'
            ).join('');
        }
        
        function updateTradeQueue(signals) {
            const container = document.getElementById('tradeQueue');
            if (!signals || signals.length === 0) {
                container.innerHTML = '<div class="text-slate-400 text-sm">سیگنال معتبری وجود ندارد</div>';
                return;
            }
            
            container.innerHTML = signals.map((s, i) => 
                '<div class="p-2 rounded-lg border ' + 
                (s.signal_type === 'LONG' ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5') + 
                ' flex justify-between items-center">' +
                    '<div class="flex items-center gap-2">' +
                        '<span class="font-bold text-slate-400">#' + (i + 1) + '</span>' +
                        '<span>' + (s.signal_type === 'LONG' ? '📈' : '📉') + '</span>' +
                        '<span class="font-bold">' + s.symbol.replace('USDT', '') + '</span>' +
                    '</div>' +
                    '<div class="flex items-center gap-2">' +
                        '<div class="w-12 bg-slate-700 rounded-full h-2">' +
                            '<div class="h-2 rounded-full bg-green-500" style="width: ' + s.score + '%"></div>' +
                        '</div>' +
                        '<span class="font-bold text-green-400">' + s.score + '</span>' +
                    '</div>' +
                '</div>'
            ).join('');
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
            loadSignals();
        }
        
        function formatNum(n) {
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
        
        function formatTime(t) {
            if (!t) return '-';
            return new Date(t).toLocaleTimeString('fa-IR');
        }
        
        function showToast(icon, msg) {
            const toast = document.getElementById('toast');
            document.getElementById('toastIcon').textContent = icon;
            document.getElementById('toastTitle').textContent = msg;
            toast.classList.remove('translate-y-20', 'opacity-0');
            setTimeout(() => toast.classList.add('translate-y-20', 'opacity-0'), 3000);
        }
    </script>
</body>
</html>
`

func handleIndex(w http.ResponseWriter, r *http.Request) {
	tmpl, _ := template.New("index").Parse(htmlTemplate)
	tmpl.Execute(w, nil)
}

// ═══════════════════════════════════════════════════════════════
// Main
// ═══════════════════════════════════════════════════════════════

func main() {
	fmt.Println("══════════════════════════════════════════════════════════════")
	fmt.Println("   🐋 Whale Hunter Pro v5.0 - Go Edition")
	fmt.Println("══════════════════════════════════════════════════════════════")
	fmt.Println()
	fmt.Println("   برای اجرا:")
	fmt.Println("   go run whale_hunter.go")
	fmt.Println()
	fmt.Println("   🌐 آدرس: http://localhost:8080")
	fmt.Println("══════════════════════════════════════════════════════════════")

	initDB()

	// Routes
	http.HandleFunc("/", handleIndex)
	http.HandleFunc("/api/config", handleConfig)
	http.HandleFunc("/api/market", handleMarket)
	http.HandleFunc("/api/signals", handleSignals)
	http.HandleFunc("/api/whales", handleWhales)
	http.HandleFunc("/api/pump-dumps", handlePumpDumps)
	http.HandleFunc("/api/account", handleAccount)
	http.HandleFunc("/api/trade-queue", handleTradeQueue)
	http.HandleFunc("/api/auto-trade/start", handleAutoTradeStart)
	http.HandleFunc("/api/auto-trade/stop", handleAutoTradeStop)
	http.HandleFunc("/api/auto-trade/stats", handleAutoTradeStats)
	http.HandleFunc("/api/trades", handleTrades)
	http.HandleFunc("/api/export", handleExport)

	log.Println("🚀 سرور در حال اجرا روی http://localhost:8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
