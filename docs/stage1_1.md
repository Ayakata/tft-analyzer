# Stage 1.1 - Capture backends

## Why

The original Stage-1 MSS implementation captures a desktop rectangle. If another
window overlaps TFT, the overlapping window becomes raw evidence.

Stage 1.1 separates capture from the recorder lifecycle and makes Windows
Graphics Capture (WGC) the default.

## Backend architecture

```text
                    CaptureBackend
                          |
                +---------+---------+
                |                   |
                v                   v
              WGC                  MSS
           (default)            (fallback)
                |                   |
                +---------+---------+
                          |
                     BackendFrame
                          |
                     MatchSession
```

## WGC behavior

- targets the exact HWND selected by `tft-analyzer windows`;
- uses an asynchronous capture thread;
- capture callback frequency is limited by `target_fps`;
- mapped native frame data is copied/encoded inside the callback;
- `MatchSession` only processes a new backend sequence once;
- cursor capture is disabled by default;
- startup waits for the first frame, allowing clean MSS fallback.

## Capture gaps

If no new frame arrives for the configured interval, Stage 1.1 writes:

```text
evidence/capture_status.jsonl
```

Possible records include `capture_started`, `capture_gap_start`,
`capture_gap_end`, `window_closed`, `capture_closed`, `stopped_by_user`, and
`capture_stopped`.

A minimized window is recorded as a gap instead of repeatedly reusing an old
frame.

## CLI

```powershell
tft-analyzer record --handle <HWND>
tft-analyzer record --handle <HWND> --backend wgc --no-fallback
tft-analyzer record --handle <HWND> --backend mss
```

## Acceptance test

1. Start TFT.
2. Start recorder with WGC.
3. Wait for several evidence frames.
4. Cover TFT completely with VS Code/browser for 10-20 seconds.
5. Return to TFT.
6. Stop recorder and open replay.

Expected: recorded visual evidence remains TFT rather than the covering app.

## 0.2.3 timing hotfix

WGC can deliver/cache its first frame while `backend.start()` is still running.
The recorder now creates the monotonic session origin before starting the
backend, so the first `EvidenceRef.timestamp_s` is always non-negative.
