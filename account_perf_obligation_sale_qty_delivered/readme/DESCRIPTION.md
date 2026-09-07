This module extends **Performance Obligations** to automatically adjust the obligation's total amount when the delivered quantity on a sale order line exceeds the ordered quantity.

## Features
* **Over-Delivery Adjustment**: Automatically recalculates and updates the total amount of the performance obligation whenever `qty_delivered` exceeds `product_uom_qty`.
* **Dynamic Re-Sync**: Restores or reduces the obligation amount if delivery quantities are corrected or updated.
