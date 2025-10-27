# Live Feed Analysis and Proposed Improvements

## Current Implementation Analysis

### Strengths Identified
1. **Robust Buffer Management**: The `feedBufCap` of 800 lines with circular buffer trimming
2. **Smart Flush Strategy**: Different flush intervals for auto-follow vs manual scrolling
3. **Channel Backpressure Detection**: Runner detects when channel is full and logs diagnostics
4. **Comprehensive Test Coverage**: Existing tests cover burst handling, buffer trimming, and flush boundaries
5. **Proper Python Integration**: `logging_utils.py` ensures `flush=True` by default

### Potential Issues Identified

#### 1. **Single-threaded Log Reading**
The current `readLogs()` function reads only one line per command cycle:
```go
func (m model) readLogs() tea.Cmd {
    // ...
    return func() tea.Msg {
        line, ok := <-ch
        if !ok {
            return nil
        }
        return logLineMsg{line: line}
    }
}
```

**Issue**: During high-volume output, this creates a bottleneck where the TUI processes one line per Bubble Tea update cycle, potentially causing backlog buildup.

#### 2. **Viewport Update Performance**
Large `SetContent()` calls can be expensive:
```go
m.runFeed.SetContent(strings.Join(m.runFeedBuf, "\n"))
```

**Issue**: When `runFeedBuf` contains hundreds of lines, the viewport rendering could cause UI stuttering.

#### 3. **Channel Capacity vs Consumer Speed**
Runner channel capacity is 2048 lines, but during burst scenarios this can still be overwhelmed if the TUI consumer is slow.

## Proposed Improvements

### 1. **Batch Log Reading**
Implement batch reading to process multiple lines per command cycle:

```go
const maxBatchSize = 50 // Maximum lines to process in one batch

func (m model) readLogsBatch() tea.Cmd {
    if m.logCh == nil {
        return nil
    }
    ch := m.logCh
    return func() tea.Msg {
        var lines []runner.Line
        for i := 0; i < maxBatchSize; i++ {
            line, ok := <-ch
            if !ok {
                break
            }
            lines = append(lines, line)

            // If channel is empty, don't wait
            select {
            default:
                continue
            case <-time.After(1 * time.Millisecond):
                break
            }
        }
        return logBatchMsg{lines: lines}
    }
}
```

### 2. **Incremental Viewport Updates**
Instead of rebuilding entire content, use incremental updates:

```go
func (m *model) incrementalViewportUpdate(newLines []string) {
    if len(newLines) == 0 {
        return
    }

    // Only append new lines to existing content
    currentContent := m.runFeed.View()
    newContent := currentContent + "\n" + strings.Join(newLines, "\n")

    // Let viewport handle the size limits
    m.runFeed.SetContent(newContent)
    m.runFeed.GotoBottom() // Always follow if new content added
}
```

### 3. **Adaptive Flush Thresholds**
Implement dynamic flush thresholds based on output rate:

```go
type flushController struct {
    lastFlush     time.Time
    outputRate    float64 // lines per second
    adaptiveStep  int
}

func (fc *flushController) shouldFlush(dirtyLines, bufferSize int) bool {
    now := time.Now()
    timeSinceFlush := now.Sub(fc.lastFlush)

    // Calculate current output rate
    if timeSinceFlush > 0 {
        fc.outputRate = float64(dirtyLines) / timeSinceFlush.Seconds()
    }

    // Adaptive flush step based on output rate
    if fc.outputRate > 20 { // High output rate
        fc.adaptiveStep = max(2, feedFollowFlushStep/2)
    } else if fc.outputRate < 5 { // Low output rate
        fc.adaptiveStep = feedFollowFlushStep * 2
    } else {
        fc.adaptiveStep = feedFollowFlushStep
    }

    return dirtyLines >= fc.adaptiveStep || bufferSize >= feedBufCap-100
}
```

### 4. **Enhanced Diagnostics**
Add more detailed diagnostics to identify exact stall points:

```go
type feedDiagnostic struct {
    timestamp          time.Time
    bufferSize         int
    dirtyLines         int
    channelBacklog     int
    processingTime     time.Duration
    renderTime         time.Duration
}

func (m *model) recordDiagnostic(start time.Time, processingTime time.Duration) {
    diag := feedDiagnostic{
        timestamp:      time.Now(),
        bufferSize:     len(m.runFeedBuf),
        dirtyLines:     m.runFeedDirtyLines,
        processingTime: processingTime,
    }

    // Store recent diagnostics for analysis
    m.diagnostics = append(m.diagnostics, diag)
    if len(m.diagnostics) > 100 {
        m.diagnostics = m.diagnostics[1:] // Keep only recent 100
    }

    // Detect potential issues
    if diag.processingTime > 100*time.Millisecond {
        log.Printf("SLOW PROCESSING: %v for buffer size %d",
            diag.processingTime, diag.bufferSize)
    }
}
```

## Implementation Priority

1. **High Priority**: Batch log reading (Issue #1) - This is the most likely cause of stalls
2. **Medium Priority**: Enhanced diagnostics - Will help identify remaining issues
3. **Low Priority**: Incremental viewport updates - Performance optimization
4. **Low Priority**: Adaptive flush thresholds - Fine-tuning for different scenarios

## Test Strategy

1. **Load Testing**: Use the existing stress test with increased duration
2. **Burst Testing**: Test with very high-frequency output bursts
3. **Long-running Tests**: Multi-hour tests to catch memory leaks or gradual degradation
4. **Memory Profiling**: Monitor memory usage during stress tests

## Expected Outcomes

These improvements should:
- Eliminate feed stalls during high-volume output
- Improve overall TUI responsiveness
- Provide better diagnostic information
- Maintain existing functionality and behavior