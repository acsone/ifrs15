## Why this module?
The `account_perf_obligation_sale` module creates performance obligations based on ordered quantities upon sale order confirmation.

When the delivered quantity on a sale order line exceeds the ordered quantity (over-delivery), the performance obligation total amount must be adjusted accordingly.

This module monitors changes to `qty_delivered` and updates the total amount of linked performance obligations whenever `qty_delivered` exceeds `product_uom_qty`.

## Companion modules
* **account_perf_obligation_sale** *(required)*: Integrates performance obligations with sale order lines.
