# Copyright 2026 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.tools import float_compare


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_perf_obligation_amount(self):
        """Recompute the obligation amount based on delivered quantity
        when qty_delivered exceeds product_uom_qty.
        """
        self.ensure_one()
        if (
            not self.product_uom_qty
            or float_compare(
                self.qty_delivered,
                self.product_uom_qty,
                precision_rounding=self.product_uom.rounding,
            )
            <= 0
        ):
            return super()._get_perf_obligation_amount()
        base_line = self._prepare_base_line_for_taxes_computation(
            quantity=self.qty_delivered
        )
        self.env["account.tax"]._add_tax_details_in_base_line(
            base_line, self.company_id
        )
        return base_line["tax_details"]["raw_total_excluded_currency"]

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if any("qty_delivered" in vals for vals in vals_list):
            lines._check_perf_obligation_over_delivery()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "qty_delivered" in vals:
            self._check_perf_obligation_over_delivery()
        return res

    def _check_perf_obligation_over_delivery(self):
        """Update obligation total_amount when delivered quantity changes."""
        for line in self:
            if line.perf_obligation_id:
                line.perf_obligation_id._update_amount_from_sources(
                    reason=_(
                        "Total amount updated following quantity delivery update "
                        "on sale line %(line)s.",
                        line=line.display_name,
                    )
                )
