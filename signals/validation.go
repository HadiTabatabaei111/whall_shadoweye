// signal validation logic

package signals

import "errors"

// ValidateSignal checks if the provided signal is valid.
func ValidateSignal(signal string) error {
    if signal == "" {
        return errors.New("signal cannot be empty")
    }
    // Add more validation logic as needed
    return nil
}