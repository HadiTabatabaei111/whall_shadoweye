package handlers

import (
    "net/http"
)

// HelloHandler responds with a hello message
func HelloHandler(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
    w.Write([]byte("Hello, World!"))
}

// GoodbyeHandler responds with a goodbye message
func GoodbyeHandler(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
    w.Write([]byte("Goodbye, World!"))
}

// ExampleHealthCheckHandler for health check endpoint
func HealthCheckHandler(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
    w.Write([]byte("OK"))
}