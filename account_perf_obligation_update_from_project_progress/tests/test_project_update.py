# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProjectUpdatePerfObligation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.partner = cls.env["res.partner"].create({"name": "Test Customer"})
        cls.income_account = cls.env["account.account"].create(
            {
                "name": "Income Recognition P&L",
                "code": "707TST.UPDATE",
                "account_type": "income",
            }
        )
        cls.asset_account = cls.env["account.account"].create(
            {
                "name": "Income Accrual BS",
                "code": "418TST.UPDATE",
                "account_type": "asset_current",
            }
        )
        cls.liability_account = cls.env["account.account"].create(
            {
                "name": "Income Deferral BS",
                "code": "487TST.UPDATE",
                "account_type": "liability_current",
            }
        )
        cls.reco_journal = cls.env["account.journal"].create(
            {
                "name": "Income Recognition Journal",
                "code": "RECOU",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.company.write(
            {
                "po_income_journal_id": cls.reco_journal.id,
                "po_income_pl_account_id": cls.income_account.id,
                "po_income_debit_bs_account_id": cls.asset_account.id,
                "po_income_credit_bs_account_id": cls.liability_account.id,
            }
        )
        cls.product_po_project = cls.env["product.product"].create(
            {
                "name": "Service with PO and Project",
                "type": "service",
                "service_tracking": "project_only",
                "perf_obligation_sale_auto_create": True,
                "property_account_income_id": cls.income_account.id,
            }
        )

    def _create_and_confirm_so(self, lines=None):
        """Helper to create and confirm a Sales Order."""
        if lines is None:
            lines = [(self.product_po_project, 1, 1000.0)]
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": product,
                            "product_uom_qty": qty,
                            "price_unit": price,
                        }
                    )
                    for product, qty, price in lines
                ],
            }
        )
        order.action_confirm()
        return order

    def test_project_update_creates_recognition_entry(self):
        """Creating a Project Update triggers income recognition on the linked PO."""
        order = self._create_and_confirm_so([(self.product_po_project.id, 1, 1000.0)])
        project = order.project_ids
        po = order.order_line.perf_obligation_id
        self.assertTrue(project)
        self.assertTrue(po)
        self.assertEqual(po.total_amount, 1000.0)
        # Create a project update at 50% progress
        self.env["project.update"].create(
            {
                "name": "Progress 50%",
                "project_id": project.id,
                "progress": 50.0,
                "date": "2026-06-01",
                "status": "on_track",
            }
        )
        lines = self.env["account.move.line"].search(
            [("perf_obligation_id", "=", po.id)]
        )
        pl_line = lines.filtered(lambda line: line.account_id == self.income_account)
        self.assertTrue(pl_line)
        self.assertEqual(pl_line.credit, 500.0)

    def test_project_update_write_updates_recognition(self):
        """Updating progress on an existing update triggers
        incremental recognition.
        """
        order = self._create_and_confirm_so([(self.product_po_project.id, 1, 1000.0)])
        project = order.project_ids
        po = order.order_line.perf_obligation_id
        update = self.env["project.update"].create(
            {
                "name": "Progress 50%",
                "project_id": project.id,
                "progress": 50.0,
                "date": "2026-06-01",
                "status": "on_track",
            }
        )
        # Update progress from 50% to 80%
        update.write({"progress": 80.0, "name": "Progress 80%"})
        lines = self.env["account.move.line"].search(
            [("perf_obligation_id", "=", po.id)]
        )
        pl_lines = lines.filtered(lambda line: line.account_id == self.income_account)
        self.assertEqual(sum(pl_lines.mapped("credit")), 800.0)

    def test_multiple_perf_obligations_raises_user_error(self):
        """Creating a Project Update for a project with >1 PO raises UserError."""
        second_product = self.env["product.product"].create(
            {
                "name": "Second Service PO",
                "type": "service",
                "service_tracking": "task_in_project",
                "perf_obligation_sale_auto_create": True,
                "property_account_income_id": self.income_account.id,
            }
        )
        order = self._create_and_confirm_so(
            [
                (self.product_po_project.id, 1, 1000.0),
                (second_product.id, 1, 500.0),
            ]
        )
        project = order.project_ids
        obligations = project._get_perf_obligations()
        self.assertEqual(len(obligations), 2)
        with self.assertRaisesRegex(
            UserError, "Multiple performance obligations found"
        ):
            self.env["project.update"].create(
                {
                    "name": "Update on Multi-PO Project",
                    "project_id": project.id,
                    "progress": 50.0,
                    "date": "2026-06-01",
                    "status": "on_track",
                }
            )

    def test_project_update_without_obligations_succeeds(self):
        """Project Update on a project with no obligations runs cleanly
        without error.
        """
        plain_project = self.env["project.project"].create({"name": "Plain Project"})
        update_plain = self.env["project.update"].create(
            {
                "name": "Plain Update",
                "project_id": plain_project.id,
                "progress": 50.0,
                "date": "2026-06-01",
                "status": "on_track",
            }
        )
        self.assertTrue(update_plain.exists())
