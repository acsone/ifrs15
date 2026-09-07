1. Create and confirm a **Sale Order** containing products configured to auto-create a Performance Obligation.
2. Set or update the **Delivered Quantity** (`qty_delivered`) on a sale order line so that it exceeds the **Ordered Quantity** (`product_uom_qty`).
3. Odoo automatically updates the **Total Amount** of the linked Performance Obligation to match the delivered amount.
4. If the delivered quantity is later reduced or corrected, the obligation total amount is updated back accordingly.
