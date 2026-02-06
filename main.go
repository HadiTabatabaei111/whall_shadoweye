// main.go
package main

import (
    "errors"
    "net/http"
    "sync"
    "time"

    "github.com/gin-gonic/gin"
)

type Signal struct {
    ID             string                 `json:"id"`
    Symbol         string                 `json:"symbol"`
    Exchange       string                 `json:"exchange"`
    MarketType     string                 `json:"market_type"`
    Side           string                 `json:"side"`
    Entry          float64                `json:"entry"`
    Sl             float64                `json:"sl"`
    Tp             float64                `json:"tp"`
    Rr             float64                `json:"rr"`
    Timeframe      string                 `json:"timeframe"`
    Title          string                 `json:"title"`
    Score          float64                `json:"score"`
    ValidityParams map[string]interface{} `json:"validity_params"`
    IsValid        bool                   `json:"is_valid"`
    ValidatedAt    float64                `json:"validated_at"`
    Source         string                 `json:"source"`
    Status         string                 `json:"status"`
}

type Position struct {
    ID        string    `json:"id"`
    Symbol    string    `json:"symbol"`
    Side      string    `json:"side"`
    Entry     float64   `json:"entry"`
    Size      float64   `json:"size"`
    CreatedAt time.Time `json:"created_at"`
    ExpireAt  time.Time `json:"expire_at"`
    Status    string    `json:"status"` // open, closed, expired
}

var (
    openPositions = map[string]Position{}
    posMu         sync.Mutex

    activeExchange string
    walletBalance  float64
    accountName    string
)

type ExchangeClient interface {
    TestConnection() error
    GetWalletBalance() (float64, string, error)
    PlaceOrder(symbol, side string, qty float64, price float64) (string, error)
    GetCurrentPrice(symbol string) (float64, error)
}

type DummyFutures struct{}

func (d *DummyFutures) TestConnection() error {
    return nil
}
func (d *DummyFutures) GetWalletBalance() (float64, string, error) {
    return 1234.56, "Hadi Futures", nil
}
func (d *DummyFutures) PlaceOrder(symbol, side string, qty float64, price float64) (string, error) {
    return "order_" + symbol + "_" + side, nil
}
func (d *DummyFutures) GetCurrentPrice(symbol string) (float64, error) {
    return 43210.5, nil
}

var client ExchangeClient = &DummyFutures{}

func CountOpenPositions() int {
    posMu.Lock()
    defer posMu.Unlock()
    count := 0
    for _, p := range openPositions {
        if p.Status == "open" {
            count++
        }
    }
    return count
}

func AddPosition(p Position) error {
    posMu.Lock()
    defer posMu.Unlock()
    if CountOpenPositions() >= 4 {
        return errors.New("MAX_OPEN_POSITIONS_REACHED")
    }
    openPositions[p.ID] = p
    return nil
}

func CleanupExpiredPositions() {
    posMu.Lock()
    defer posMu.Unlock()
    now := time.Now()
    for id, p := range openPositions {
        if p.Status == "open" && p.ExpireAt.Before(now) {
            p.Status = "expired"
            openPositions[id] = p
        }
    }
}

func TestAPI(c *gin.Context) {
    var req struct {
        Exchange   string `json:"exchange"`
        ApiKey     string `json:"api_key"`
        ApiSecret  string `json:"api_secret"`
        Passphrase string `json:"passphrase"`
    }
    if err := c.BindJSON(&req); err != nil {
        c.JSON(400, gin.H{"error": "INVALID_REQUEST"})
        return
    }

    // اینجا بعداً client واقعی Bybit/OKX را می‌سازی
    activeExchange = req.Exchange

    if err := client.TestConnection(); err != nil {
        c.JSON(400, gin.H{"status": "error", "message": err.Error()})
        return
    }

    bal, name, _ := client.GetWalletBalance()
    walletBalance = bal
    accountName = name

    c.JSON(200, gin.H{
        "status":         "connected",
        "exchange":       activeExchange,
        "wallet_balance": walletBalance,
        "account_name":   accountName,
    })
}

func ReceiveSignal(c *gin.Context) {
    var sig Signal
    if err := c.BindJSON(&sig); err != nil {
        c.JSON(400, gin.H{"error": "INVALID_SIGNAL"})
        return
    }

    if !sig.IsValid {
        c.JSON(200, gin.H{"status": "ignored"})
        return
    }

    if CountOpenPositions() >= 4 {
        c.JSON(200, gin.H{"status": "rejected", "reason": "MAX_OPEN_POSITIONS"})
        return
    }

    price, _ := client.GetCurrentPrice(sig.Symbol)
    qty := 0.01 // بعداً بر اساس ریسک واقعی محاسبه کن

    orderID, err := client.PlaceOrder(sig.Symbol, sig.Side, qty, price)
    if err != nil {
        c.JSON(500, gin.H{"status": "error", "message": err.Error()})
        return
    }

    p := Position{
        ID:        orderID,
        Symbol:    sig.Symbol,
        Side:      sig.Side,
        Entry:     price,
        Size:      qty,
        CreatedAt: time.Now(),
        ExpireAt:  time.Now().Add(20 * time.Minute),
        Status:    "open",
    }
    _ = AddPosition(p)

    c.JSON(200, gin.H{"status": "executed", "order_id": orderID})
}

func GetPositions(c *gin.Context) {
    posMu.Lock()
    defer posMu.Unlock()
    list := []Position{}
    for _, p := range openPositions {
        list = append(list, p)
    }
    c.JSON(200, list)
}

func GetPrice(c *gin.Context) {
    symbol := c.Query("symbol")
    price, _ := client.GetCurrentPrice(symbol)
    c.JSON(200, gin.H{"symbol": symbol, "price": price})
}

func GetWallet(c *gin.Context) {
    c.JSON(200, gin.H{
        "exchange":       activeExchange,
        "wallet_balance": walletBalance,
        "account_name":   accountName,
    })
}

func main() {
    go func() {
        for {
            CleanupExpiredPositions()
            time.Sleep(5 * time.Second)
        }
    }()

    r := gin.Default()
    r.POST("/api/test", TestAPI)
    r.POST("/api/signals", ReceiveSignal)
    r.GET("/api/positions", GetPositions)
    r.GET("/api/price", GetPrice)
    r.GET("/api/wallet", GetWallet)

    r.StaticFile("/", "./index.html") // داشبورد

    r.Run(":8080")
}
