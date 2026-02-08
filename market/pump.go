package main

import (
	"fmt"
	"time"
)

// Pump and Dump Detection Logic
func detectPumpDump(prices []float64, threshold float64) {
	// Example logic to detect pump and dump based on price movements
	if len(prices) < 2 {
		fmt.Println("Not enough data to analyze")
		return
	}

	initialPrice := prices[0]
	for _, price := range prices[1:] {
		change := (price - initialPrice) / initialPrice * 100
		if change > threshold {
			fmt.Printf("Pump detected! Price changed by %.2f%%\n", change)
			return
		}
	}
	fmt.Println("No pump detected")
}

func main() {
	// Test data for monitoring price changes
	prices := []float64{100, 120, 130, 110, 105, 90}
	threshold := 10.0 // 10% threshold
	detectPumpDump(prices, threshold)
}