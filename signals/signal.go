package signals

import (
	"math/rand"
	"time"
)

// GenerateSignals creates a slice of random signals for the given duration and frequency.
func GenerateSignals(duration time.Duration, frequency int) []float64 {
	rand.Seed(time.Now().UnixNano())
	numSamples := int(duration.Seconds()) * frequency
	signals := make([]float64, numSamples)

	for i := 0; i < numSamples; i++ {
		signals[i] = rand.Float64() // Generate random signal between 0 and 1
	}

	return signals
}