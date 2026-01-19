//go:build !windows

package runner

import (
	"os"
	"os/exec"
	"syscall"
)

func setupProcessGroup(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
}

func interruptProcess(cmd *exec.Cmd) error {
	if cmd.Process == nil || (cmd.ProcessState != nil && cmd.ProcessState.Exited()) {
		return nil
	}
	if err := syscall.Kill(-cmd.Process.Pid, syscall.SIGINT); err != nil {
		if err == syscall.ESRCH || err == syscall.EINVAL {
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
	if err := syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL); err != nil {
		if err == syscall.ESRCH || err == syscall.EINVAL {
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
	if err := syscall.Kill(-proc.Pid, syscall.SIGINT); err != nil {
		if err == syscall.ESRCH || err == syscall.EINVAL {
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
	if err := syscall.Kill(-proc.Pid, syscall.SIGKILL); err != nil {
		if err == syscall.ESRCH || err == syscall.EINVAL {
			return nil
		}
		return err
	}
	return nil
}
