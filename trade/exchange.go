// exchange.go

package trade

import (
    "fmt"
    "net/http"
    "io/ioutil"
)

// ExchangeAPI is a struct to hold the configuration for the exchange API
type ExchangeAPI struct {
    BaseURL string
}

// NewExchangeAPI initializes a new ExchangeAPI
func NewExchangeAPI(baseURL string) *ExchangeAPI {
    return &ExchangeAPI{BaseURL: baseURL}
}

// GetPrice fetches the current price from the exchange API
func (api *ExchangeAPI) GetPrice(symbol string) (float64, error) {
    url := fmt.Sprintf("%s/price?symbol=%s", api.BaseURL, symbol)
    resp, err := http.Get(url)
    if err != nil {
        return 0, err
    }
    defer resp.Body.Close()

    body, err := ioutil.ReadAll(resp.Body)
    if err != nil {
        return 0, err
    }

    var price float64
    // Assuming the API returns price in JSON format
    if err := json.Unmarshal(body, &price); err != nil {
        return 0, err
    }

    return price, nil
}