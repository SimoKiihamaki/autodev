//go:build windows

package runner

import (
	"errors"
	"os"
	"os/exec"
	"syscall"
)

func setupProcessGroup(cmd *exec.Cmd) {
	if cmd.SysProcAttr == nil {
		cmd.SysProcAttr = &syscall.SysProcAttr{}
	}
	cmd.SysProcAttr.CreationFlags |= syscall.CREATE_NEW_PROCESS_GROUP
}

func interruptProcess(cmd *exec.Cmd) error {
	if cmd.Process == nil || (cmd.ProcessState != nil && cmd.ProcessState.Exited()) {
		return nil
	}
	if err := cmd.Process.Signal(os.Interrupt); err != nil {
		if errors.Is(err, os.ErrProcessDone) {
			return nil
		}
		return err
	}
	return nil
}

func forceKillProcess(cmd *exec.Cmd) error {
	if cmd.Process == nil || (cmd.ProcessState != nil && cmd.ProcessState.Exited()) {
		return nil
	}
	if err := cmd.Process.Kill(); err != nil {
		if errors.Is(err, os.ErrProcessDone) {
			return nil
		}
		return err
	}
	return nil
}

// interruptProcessCmd interrupts a process using the captured process reference.
// This avoids data races with cmd.Wait() which writes to cmd.ProcessState.
func interruptProcessCmd(proc *os.Process) error {
	if proc == nil {
		return nil
	}
	if err := proc.Signal(os.Interrupt); err != nil {
		if errors.Is(err, os.ErrProcessDone) {
			return nil
		}
		return err
	}
	return nil
}

// forceKillProcessCmd forcefully kills a process using the captured process reference.
// This avoids data races with cmd.Wait() which writes to cmd.ProcessState.
func forceKillProcessCmd(proc *os.Process) error {
	if proc == nil {
		return nil
	}
	if err := proc.Kill(); err != nil {
		if errors.Is(err, os.ErrProcessDone) {
			return nil
		}
		return err
	}
	return nil
}
