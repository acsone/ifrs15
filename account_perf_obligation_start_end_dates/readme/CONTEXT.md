## Why this module?

The base *Performance Obligations* module handles recognition and scheduling
but does not define when an obligation starts and ends, nor how to compute
the recognized amount at a given date. This is intentional: different
businesses use different methods.

This module provides the most common implementation: a **daily pro-rata**
calculation over a fixed date range. It is the recommended starting point
for any company recognizing revenue or expenses over a defined contract period.

## Companion modules

- **account_perf_obligation** *(required)*: provides the core performance
  obligation object and recognition engine.
- **account_perf_obligation_auto_schedule** *(optional)*: processes flagged
  obligations automatically and asynchronously via `queue_job`.
