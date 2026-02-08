package market

import (
	"fmt"
	"time"
)

// DetectWhales checks for large whale transactions.
func DetectWhales(transactions []float64, threshold float64) []float64 {
	var whales []float64
	for _, amount := range transactions {
		if amount >= threshold {
			whales = append(whales, amount)
		}
	}
	return whales
}

func main() {
	// Example transactions
	transactions := []float64{100, 5000, 1500, 20000, 300}
	threshold := 1000.0

	whaleTransactions := DetectWhales(transactions, threshold)
	fmt.Println("Whale Transactions:", whaleTransactions)
	fmt.Println("Detection Time:", time.Now().UTC())
}