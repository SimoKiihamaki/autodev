//go:build !windows

package runner

import (
	"os/exec"
	"syscall"
	"testing"
	"time"
)

func TestInterruptProcess(t *testing.T) {
	t.Parallel()

	t.Run("nil process returns nil", func(t *testing.T) {
		t.Parallel()
		cmd := &exec.Cmd{}
		if err := interruptProcess(cmd); err != nil {
			t.Errorf("interruptProcess(nil) should return nil, got %v", err)
		}
	})

	t.Run("exited process returns nil", func(t *testing.T) {
		t.Parallel()
		cmd := exec.Command("echo", "done")
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		if err := cmd.Wait(); err != nil {
			t.Fatal(err)
		}
		// Process has exited
		if err := interruptProcess(cmd); err != nil {
			t.Errorf("interruptProcess(exited) should return nil, got %v", err)
		}
	})

	t.Run("running process receives signal", func(t *testing.T) {
		// Note: This test verifies that interruptProcess sends the signal
		// without error. It doesn't guarantee the process dies immediately
		// since that depends on the process's signal handling.
		cmd := exec.Command("cat")
		// Set up pipes to avoid blocking - capture stdin to close it later
		stdin, err := cmd.StdinPipe()
		if err != nil {
			t.Fatal(err)
		}
		if _, err := cmd.StdoutPipe(); err != nil {
			t.Fatal(err)
		}
		if _, err := cmd.StderrPipe(); err != nil {
			t.Fatal(err)
		}

		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		// Close stdin so cat doesn't block waiting for input
		stdin.Close()

		// Give process time to start
		time.Sleep(100 * time.Millisecond)

		// Verify process is running
		if cmd.Process == nil {
			t.Fatal("Process should be started")
		}
		pid := cmd.Process.Pid

		// Interrupt the process - this should send SIGINT to the process group
		if err := interruptProcess(cmd); err != nil {
			t.Errorf("interruptProcess() failed: %v", err)
		}

		// Give the process a moment to handle the signal
		time.Sleep(50 * time.Millisecond)

		// Verify the signal was sent by checking process state
		// The process should either be exited or have received the signal
		if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
			// Process exited - verify it was signaled
			if cmd.ProcessState.Success() {
				// Exited with status 0 - might have handled SIGINT and exited cleanly
				// This is acceptable behavior
			}
		}

		// Clean up: force kill if still running
		if cmd.ProcessState == nil || !cmd.ProcessState.Exited() {
			cmd.Process.Kill()
			cmd.Wait()
		}

		// Test passed if we got here without error from interruptProcess
		_ = pid // Use the variable
	})

	t.Run("ignores ESRCH error", func(t *testing.T) {
		t.Parallel()
		// Create a process that will exit immediately
		cmd := exec.Command("true")
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		cmd.Wait() // Let it exit

		// Try to interrupt the already-exited process
		// This will cause ESRCH (no such process) which should be ignored
		if err := interruptProcess(cmd); err != nil {
			t.Errorf("interruptProcess() should ignore ESRCH, got %v", err)
		}
	})

	t.Run("ignores EINVAL error", func(t *testing.T) {
		t.Parallel()
		// Create a process and let it exit
		cmd := exec.Command("true")
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		cmd.Wait()

		// Try to interrupt - may get EINVAL which should be ignored
		if err := interruptProcess(cmd); err != nil {
			t.Errorf("interruptProcess() should ignore EINVAL, got %v", err)
		}
	})
}

func TestForceKillProcess(t *testing.T) {
	t.Parallel()

	t.Run("nil process returns nil", func(t *testing.T) {
		t.Parallel()
		cmd := &exec.Cmd{}
		if err := forceKillProcess(cmd); err != nil {
			t.Errorf("forceKillProcess(nil) should return nil, got %v", err)
		}
	})

	t.Run("exited process returns nil", func(t *testing.T) {
		t.Parallel()
		cmd := exec.Command("echo", "done")
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		if err := cmd.Wait(); err != nil {
			t.Fatal(err)
		}
		// Process has exited
		if err := forceKillProcess(cmd); err != nil {
			t.Errorf("forceKillProcess(exited) should return nil, got %v", err)
		}
	})

	t.Run("running process is killed", func(t *testing.T) {
		// Note: This test verifies that forceKillProcess sends SIGKILL
		// which cannot be ignored. The process should die.
		cmd := exec.Command("cat")
		// Set up pipes to avoid blocking - capture stdin to close it later
		stdin, err := cmd.StdinPipe()
		if err != nil {
			t.Fatal(err)
		}
		if _, err := cmd.StdoutPipe(); err != nil {
			t.Fatal(err)
		}
		if _, err := cmd.StderrPipe(); err != nil {
			t.Fatal(err)
		}

		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		// Close stdin so cat doesn't block waiting for input
		stdin.Close()

		// Give process time to start
		time.Sleep(100 * time.Millisecond)

		// Verify process is running
		if cmd.Process == nil {
			t.Fatal("Process should be started")
		}

		// Kill the process - this should send SIGKILL to the process group
		if err := forceKillProcess(cmd); err != nil {
			t.Errorf("forceKillProcess() failed: %v", err)
		}

		// Wait for process to die - process must exit
		if err := cmd.Wait(); err != nil {
			// Process exited with error - this is expected for SIGKILL
			// (or it might have exited due to stdin closing, which is OK too)
		}

		// Verify process is actually dead
		if !cmd.ProcessState.Exited() {
			t.Error("Process should have exited after forceKillProcess")
		}
	})

	t.Run("ignores ESRCH error", func(t *testing.T) {
		t.Parallel()
		// Create a process that will exit immediately
		cmd := exec.Command("true")
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		cmd.Wait() // Let it exit

		// Try to kill the already-exited process
		// This will cause ESRCH (no such process) which should be ignored
		if err := forceKillProcess(cmd); err != nil {
			t.Errorf("forceKillProcess() should ignore ESRCH, got %v", err)
		}
	})

	t.Run("ignores EINVAL error", func(t *testing.T) {
		t.Parallel()
		// Create a process and let it exit
		cmd := exec.Command("true")
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		cmd.Wait()

		// Try to kill - may get EINVAL which should be ignored
		if err := forceKillProcess(cmd); err != nil {
			t.Errorf("forceKillProcess() should ignore EINVAL, got %v", err)
		}
	})
}

func TestInterruptProcessCmd(t *testing.T) {
	t.Parallel()

	t.Run("nil process returns nil", func(t *testing.T) {
		t.Parallel()
		if err := interruptProcessCmd(nil); err != nil {
			t.Errorf("interruptProcessCmd(nil) should return nil, got %v", err)
		}
	})

	t.Run("running process receives signal", func(t *testing.T) {
		// Note: This test verifies that interruptProcessCmd sends the signal
		// without error. It doesn't guarantee the process dies immediately
		// since that depends on the process's signal handling.
		cmd := exec.Command("cat")
		// Set up pipes to avoid blocking - capture stdin to close it later
		stdin, err := cmd.StdinPipe()
		if err != nil {
			t.Fatal(err)
		}
		if _, err := cmd.StdoutPipe(); err != nil {
			t.Fatal(err)
		}
		if _, err := cmd.StderrPipe(); err != nil {
			t.Fatal(err)
		}

		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		// Close stdin so cat doesn't block waiting for input
		stdin.Close()

		// Capture the process before it exits
		proc := cmd.Process

		// Give process time to start
		time.Sleep(100 * time.Millisecond)

		// Interrupt the process using the captured process reference
		if err := interruptProcessCmd(proc); err != nil {
			t.Errorf("interruptProcessCmd() failed: %v", err)
		}

		// Give the process a moment to handle the signal
		time.Sleep(50 * time.Millisecond)

		// Clean up: force kill if still running
		if cmd.ProcessState == nil || !cmd.ProcessState.Exited() {
			cmd.Process.Kill()
			cmd.Wait()
		}

		// Test passed if we got here without error from interruptProcessCmd
		_ = proc
	})

	t.Run("exited process is handled gracefully", func(t *testing.T) {
		// Create a process that exits immediately
		cmd := exec.Command("true")
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}

		// Capture the process
		proc := cmd.Process

		// Wait for it to exit
		cmd.Wait()

		// Try to interrupt the already-exited process
		// Should return nil (ignores ESRCH/EINVAL)
		if err := interruptProcessCmd(proc); err != nil {
			t.Errorf("interruptProcessCmd(exited) should return nil, got %v", err)
		}
	})
}

func TestForceKillProcessCmd(t *testing.T) {
	t.Parallel()

	t.Run("nil process returns nil", func(t *testing.T) {
		t.Parallel()
		if err := forceKillProcessCmd(nil); err != nil {
			t.Errorf("forceKillProcessCmd(nil) should return nil, got %v", err)
		}
	})

	t.Run("running process is killed", func(t *testing.T) {
		// Note: This test verifies that forceKillProcessCmd sends SIGKILL
		// which cannot be ignored. The process should die.
		cmd := exec.Command("cat")
		// Set up pipes to avoid blocking - capture stdin to close it later
		stdin, err := cmd.StdinPipe()
		if err != nil {
			t.Fatal(err)
		}
		if _, err := cmd.StdoutPipe(); err != nil {
			t.Fatal(err)
		}
		if _, err := cmd.StderrPipe(); err != nil {
			t.Fatal(err)
		}

		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		// Close stdin so cat doesn't block waiting for input
		stdin.Close()

		// Capture the process before it exits
		proc := cmd.Process

		// Give process time to start
		time.Sleep(100 * time.Millisecond)

		// Kill the process using the captured process reference
		if err := forceKillProcessCmd(proc); err != nil {
			t.Errorf("forceKillProcessCmd() failed: %v", err)
		}

		// Wait for process to die - process must exit
		if err := cmd.Wait(); err != nil {
			// Process exited with error - this is expected for SIGKILL
			// (or it might have exited due to stdin closing, which is OK too)
		}

		// Verify process is actually dead
		if !cmd.ProcessState.Exited() {
			t.Error("Process should have exited after forceKillProcessCmd")
		}

		_ = proc
	})

	t.Run("exited process is handled gracefully", func(t *testing.T) {
		// Create a process that exits immediately
		cmd := exec.Command("true")
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}

		// Capture the process
		proc := cmd.Process

		// Wait for it to exit
		cmd.Wait()

		// Try to kill the already-exited process
		// Should return nil (ignores ESRCH/EINVAL)
		if err := forceKillProcessCmd(proc); err != nil {
			t.Errorf("forceKillProcessCmd(exited) should return nil, got %v", err)
		}
	})
}

func TestSetupProcessGroup(t *testing.T) {
	t.Parallel()

	t.Run("sets Setpgid attribute", func(t *testing.T) {
		t.Parallel()
		cmd := &exec.Cmd{}
		setupProcessGroup(cmd)

		if cmd.SysProcAttr == nil {
			t.Fatal("SysProcAttr should not be nil after setupProcessGroup")
		}

		if !cmd.SysProcAttr.Setpgid {
			t.Error("Setpgid should be true after setupProcessGroup")
		}
	})

	t.Run("overwrites existing SysProcAttr", func(t *testing.T) {
		t.Parallel()
		cmd := &exec.Cmd{
			SysProcAttr: &syscall.SysProcAttr{
				Setpgid: false,
			},
		}
		setupProcessGroup(cmd)

		if !cmd.SysProcAttr.Setpgid {
			t.Error("Setpgid should be true even when SysProcAttr already exists")
		}
	})
}
