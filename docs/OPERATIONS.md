# Operate one GPU server

`strata-sprint serve` runs the pinned upstream HTTP server directly. It has no platform account, remote notebook session, client adaptation layer or conversation compression component. Upstream handles API requests and its own one-sequence queue; Sprint manages the process it starts.

## Ownership and recovery

- A lock prevents two supervisors from owning the same state directory. The listening port is checked before a start.
- The wrapper and native engine run in a new, owned process group. A wrapper exit cleans up a surviving child before a replacement starts.
- An exited wrapper retries after 2, 4, 8… seconds, capped at 60. A stable minute resets the backoff.
- A still-running wrapper is replaced only after three observations of **explicitly unloaded health plus an observably absent native child**, after the native child was seen or the five-minute startup grace has elapsed.
- Unknown health, missing process visibility and a live native engine are preserved. A health timeout alone does not establish that an inference can be interrupted safely.
- SIGINT/SIGTERM stop the owned group and stop recovery. `--once` disables retries. An explicit normal exit is respected.

The supervisor **never resends an inference request**. A client whose request lost its connection must handle the error. Application tools may have side effects; the caller should determine what completed before trying again.

## State and logs

`--state-dir` contains a lock and `status.json` with readiness, process presence and recovery metadata. It contains no prompt or answer content. Generated configs are written as private files. Upstream stdout/stderr stays attached to the launching terminal or service log; configure retention in the service manager. Upstream's optional request monitor can retain content, so review its settings before enabling it.

The profile keeps at most four parked states within a 16 GiB host-memory budget. A state may be skipped or evicted if the RAM floor cannot be maintained. A new process starts with a cold cache. A model restart does not restore a lost in-flight generation or the application's task state.

## systemd example

Edit the absolute paths and user in [`deploy/strata-sprint.service`](../deploy/strata-sprint.service), then install it with your normal administrator workflow. The unit uses an authenticated private config, standard restart handling and a graceful stop timeout. Run `strata-sprint doctor` as the service user first. Do not point both a terminal supervisor and systemd at the same GPU server.

## Validation status

The GPU profile has the published finite A/B and precision measurements. The extracted standalone supervisor has CPU fixture tests, including a real orphan-process cleanup test on Linux. Those checks cover observed exit handling, not every driver failure. A permanently hung live GPU process is deliberately not killed on ambiguous evidence.

This release is **0.1.0**, with one validated hardware/model profile. It has no multi-day availability certification. Before service use, perform your own soak test with representative inputs, queue depth, client cancellations, memory pressure, disk limits and driver events. Report failures with redacted metadata and exact versions through the issue templates.
