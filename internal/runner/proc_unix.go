//go:build !windows

package runner

import (
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
