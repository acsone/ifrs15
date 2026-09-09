# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import _, api, models
from odoo.exceptions import UserError


class ProjectUpdate(models.Model):
    _inherit = "project.update"

    def _get_perf_obligation_description(self):
        """Return the project update name for the recognition entry description."""
        self.ensure_one()
        return self.name

    def _process_perf_obligation_recognition(self):
        """Recognize income on performance obligations linked to the project
        based on the progress percentage.
        """
        for update in self:
            project = update.project_id
            if not project:
                continue
            obligations = project._get_perf_obligations()
            if not obligations:
                continue
            if len(obligations) > 1:
                raise UserError(
                    _(
                        "Multiple performance obligations found for project %s. "
                        "Only single performance obligation projects "
                        "are currently supported.",
                        project.display_name,
                    )
                )
            description = update._get_perf_obligation_description()
            amount_to_recognize = obligations.total_amount * (update.progress / 100.0)
            obligations._recognize(
                amount_to_recognize=amount_to_recognize,
                date=update.date,
                description=description,
            )

    @api.model_create_multi
    def create(self, vals_list):
        updates = super().create(vals_list)
        updates._process_perf_obligation_recognition()
        return updates

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {"progress", "date", "name", "project_id"}
        if vals.keys() & trigger_fields:
            self._process_perf_obligation_recognition()
        return res
