package main

import (
    "fmt"
    "time"
)

// AutoTrade struct defines the properties of the trading system
type AutoTrade struct {
    Symbol   string
    Quantity int
    Interval time.Duration
}

// ExecuteTrade simulates executing a trade
func (t *AutoTrade) ExecuteTrade() {
    fmt.Printf("Executing trade for %s with quantity %d\n", t.Symbol, t.Quantity)
    // Simulate trade execution logic here
}

// Start begins the automatic trading process
func (t *AutoTrade) Start() {
    ticker := time.NewTicker(t.Interval)
    defer ticker.Stop()
    for range ticker.C {
        t.ExecuteTrade()
    }
}

func main() {
    trader := AutoTrade{Symbol: "AAPL", Quantity: 10, Interval: 1 * time.Minute}
    fmt.Println("Starting auto trading system...")
    trader.Start()
}