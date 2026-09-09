# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class ProjectProject(models.Model):
    _inherit = "project.project"

    def _get_perf_obligations(self):
        """Return all performance obligations linked to this project via its
        Sales Order Lines.
        """
        self.ensure_one()
        sale_lines = self._get_sale_order_items()
        if self.sale_order_id:
            sale_lines |= self.sale_order_id.order_line
        return sale_lines.mapped("perf_obligation_id")
