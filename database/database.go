package database

import (
    "database/sql"
    "log"

    _ "github.com/mattn/go-sqlite3"
)

var db *sql.DB

// InitDB initializes the database connection
func InitDB(dataSourceName string) {
    var err error
    db, err = sql.Open("sqlite3", dataSourceName)
    if err != nil {
        log.Fatalf("Failed to open database: %v", err)
    }
}

// CreateTable creates a sample table
func CreateTable() {
    createTableSQL := `CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    );`
    if _, err := db.Exec(createTableSQL); err != nil {
        log.Fatalf("Failed to create table: %v", err)
    }
}

// InsertItem inserts a new item into the database
func InsertItem(name string) {
    insertSQL := `INSERT INTO items (name) VALUES (?);`
    if _, err := db.Exec(insertSQL, name); err != nil {
        log.Fatalf("Failed to insert item: %v", err)
    }
}

// CloseDB closes the database connection
func CloseDB() {
    if err := db.Close(); err != nil {
        log.Fatalf("Failed to close database: %v", err)
    }
}