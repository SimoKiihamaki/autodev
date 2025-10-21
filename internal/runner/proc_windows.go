//go:build windows

package runner

import (
	"os"
	"os/exec"
)

func setupProcessGroup(cmd *exec.Cmd) {}

func interruptProcess(cmd *exec.Cmd) error {
	if cmd.Process == nil {
		return nil
	}
	return cmd.Process.Signal(os.Interrupt)
}

func forceKillProcess(cmd *exec.Cmd) error {
	if cmd.Process == nil {
		return nil
	}
	return cmd.Process.Kill()
}
