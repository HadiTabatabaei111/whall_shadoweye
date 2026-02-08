package market

import (
    "encoding/json"
    "fmt"
    "net/http"
)

// FetchAPI fetches data from the given API endpoint.
func FetchAPI(endpoint string) (interface{}, error) {
    response, err := http.Get(endpoint)
    if err != nil {
        return nil, err
    }
    defer response.Body.Close()

    if response.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("unexpected status: %s", response.Status)
    }

    var data interface{}
    if err := json.NewDecoder(response.Body).Decode(&data); err != nil {
        return nil, err
    }

    return data, nil
}