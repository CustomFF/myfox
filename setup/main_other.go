//go:build !windows

package main

import (
	"fmt"
	"os"
)

// Built for Windows only; elsewhere it exists for the tests.
func main() {
	fmt.Fprintln(os.Stderr, "MyFox-Setup.exe is for Windows.")
	os.Exit(1)
}
