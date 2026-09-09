This module integrates project tracking with IFRS 15 Performance Obligations (`account_perf_obligation` and `account_perf_obligation_sale`).
It automatically computes and posts revenue recognition entries whenever a Project Update is created or modified.

Based on the completion progress percentage reported on the Project Update, the module calculates the cumulative amount
to recognize: total_amount * (progress / 100), and triggers the recognition entry using the Project Update date and name.
