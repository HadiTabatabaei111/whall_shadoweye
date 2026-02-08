// config/config.go

package config

import (
	"encoding/json"
	"io/ioutil"
	"os"
)

type Config struct {
	Port    string `json:"port"`
	DBName  string `json:"db_name"`
	DBUser  string `json:"db_user"`
	DBPass  string `json:"db_pass"`
}

func LoadConfig(file string) (*Config, error) {
	config := &Config{}
	data, err := ioutil.ReadFile(file)
	if err != nil {
		return nil, err
	}

	if err := json.Unmarshal(data, config); err != nil {
		return nil, err
	}
	return config, nil
}