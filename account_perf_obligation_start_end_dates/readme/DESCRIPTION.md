This module extends [Performance Obligations (IFRS 15)](../account_perf_obligation)
to support time-based income and expense recognition using **start and end dates**.

## Features

- **Daily pro-rata recognition**: automatically computes the amount to recognize
  at any given date based on the obligation's date range.
- **Automatic schedule generation**: creates draft recognition entries for each
  month-end from start date to end date, skipping periods already covered by
  posted entries.
- **End date shortening**: if the end date is moved before the last posted entry,
  a single corrective draft entry is generated to unwind the excess without
  touching already-posted entries.
- **Schedule synchronization**: changes to start date or end date automatically
  flag the obligation for regeneration, in addition to the triggers from the
  base module (total amount, recognition method, linked journal items).
- **Extensible architecture**: alternative computation methods (e.g. full-month
  based) can be added by extending the selection field and implementing the
  corresponding method.
