## Developer extensibility

**Add a new recognition method**

1. Extend the `recognition_at_date_method` selection field on `perf.obligation`
   with a new key (e.g. `"monthly"`).
2. Implement the corresponding `_compute_amount_to_recognize_monthly(date)`
   method on the same model.
3. Override `_supports_schedule()` and `_get_schedule_dates()` if the new
   method should support schedule generation.
4. Override `_get_schedule_start_date()` or `_get_schedule_end_date()` if
   the schedule boundaries need additional constraints.

**Add new trigger fields**

Override `_get_recognition_trigger_fields()` and append the field names to
the returned list. This module already adds `start_date` and `end_date` to
the base list.
