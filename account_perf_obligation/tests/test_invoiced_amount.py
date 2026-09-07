# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.exceptions import UserError

from .common import PerfObligationCommon


class TestInvoicedAmount(PerfObligationCommon):
    """Test invoiced_amount compute field and is_over_invoiced search/compute
    methods."""

    def test_invoiced_amount_initial_zero(self):
        """Without any journal items, invoiced_amount is 0.0 and is_over_invoiced is
        False."""
        po = self._create_obligation(perf_type="income", total_amount=1000)
        self.assertEqual(po.invoiced_amount, 0.0)
        self.assertFalse(po.is_over_invoiced)

    def test_invoiced_amount_income_with_invoice(self):
        """Invoiced amount on income obligation matches invoice line balance."""
        po = self._create_obligation(perf_type="income", total_amount=1000)
        self._create_and_post_move(
            self.sale_journal,
            [
                (self.receivable_account, 1200, 0, False),
                (self.income_account, 0, 1200, po),
            ],
            date="2026-01-01",
        )
        self.assertEqual(po.invoiced_amount, 1200.0)
        # Tests _compute_is_over_invoiced directly
        self.assertTrue(po.is_over_invoiced)

    def test_invoiced_amount_income_remains_same_after_recognition(self):
        """Invoiced amount is invariant under recognition entries."""
        po = self._create_obligation(perf_type="income", total_amount=1000)
        self._create_and_post_move(
            self.sale_journal,
            [
                (self.receivable_account, 1000, 0, False),
                (self.income_account, 0, 1000, po),
            ],
            date="2026-01-01",
        )
        self.assertEqual(po.invoiced_amount, 1000.0)
        self.assertFalse(po.is_over_invoiced)
        # Recognize 500
        po._recognize(500, "2026-01-31", "Jan reco")
        self.assertEqual(po.invoiced_amount, 1000.0)
        self.assertFalse(po.is_over_invoiced)

    def test_invoiced_amount_expense_with_bill(self):
        """Invoiced amount on expense obligation matches vendor bill line balance."""
        po = self._create_obligation(perf_type="expense", total_amount=500)
        self._create_and_post_move(
            self.purchase_journal,
            [
                (self.payable_account, 0, 600, False),
                (self.expense_account, 600, 0, po),
            ],
            date="2026-01-01",
        )
        self.assertEqual(po.invoiced_amount, 600.0)
        self.assertTrue(po.is_over_invoiced)

    def test_search_is_over_invoiced_income(self):
        """Searching for over-invoiced income obligations returns expected POs."""
        po_normal = self._create_obligation(perf_type="income", total_amount=1000)
        self._create_and_post_move(
            self.sale_journal,
            [
                (self.receivable_account, 1000, 0, False),
                (self.income_account, 0, 1000, po_normal),
            ],
        )
        po_over = self._create_obligation(perf_type="income", total_amount=1000)
        self._create_and_post_move(
            self.sale_journal,
            [
                (self.receivable_account, 1200, 0, False),
                (self.income_account, 0, 1200, po_over),
            ],
        )
        # Check direct record compute
        self.assertFalse(po_normal.is_over_invoiced)
        self.assertTrue(po_over.is_over_invoiced)
        # Check ORM domain search
        res_over = self.env["perf.obligation"].search([("is_over_invoiced", "=", True)])
        self.assertIn(po_over, res_over)
        self.assertNotIn(po_normal, res_over)
        res_not_over = self.env["perf.obligation"].search(
            [("is_over_invoiced", "=", False)]
        )
        self.assertIn(po_normal, res_not_over)
        self.assertNotIn(po_over, res_not_over)

    def test_search_is_over_invoiced_expense(self):
        """Searching for over-invoiced expense obligations returns expected POs."""
        po_normal = self._create_obligation(perf_type="expense", total_amount=500)
        self._create_and_post_move(
            self.purchase_journal,
            [
                (self.payable_account, 0, 500, False),
                (self.expense_account, 500, 0, po_normal),
            ],
        )
        po_over = self._create_obligation(perf_type="expense", total_amount=500)
        self._create_and_post_move(
            self.purchase_journal,
            [
                (self.payable_account, 0, 700, False),
                (self.expense_account, 700, 0, po_over),
            ],
        )
        # Check direct record compute
        self.assertFalse(po_normal.is_over_invoiced)
        self.assertTrue(po_over.is_over_invoiced)
        # Check ORM domain search
        res_over = self.env["perf.obligation"].search([("is_over_invoiced", "=", True)])
        self.assertIn(po_over, res_over)
        self.assertNotIn(po_normal, res_over)

    def test_search_is_over_invoiced_invalid_operator(self):
        """Unsupported search operators raise UserError."""
        with self.assertRaises(UserError):
            self.env["perf.obligation"]._search_is_over_invoiced(">", True)

    def test_search_is_over_invoiced_invalid_value(self):
        """Non-boolean search values raise UserError."""
        with self.assertRaises(UserError):
            self.env["perf.obligation"]._search_is_over_invoiced("=", "invalid")

    def test_recognized_amount_and_is_over_recognized_income(self):
        """Test recognized amount and over-recognized search for income POs."""
        po = self._create_obligation(perf_type="income", total_amount=1000)
        self._create_and_post_move(
            self.sale_journal,
            [
                (self.receivable_account, 500, 0, False),
                (self.inc_credit_bs, 0, 500, po),
            ],
            date="2026-01-01",
        )
        self.assertEqual(po.invoiced_amount, 500.0)
        self.assertEqual(po.recognized_amount, 0.0)
        self.assertFalse(po.is_over_recognized)
        # Recognize 800.0 (recognized > invoiced)
        po._recognize(800, "2026-01-31", "Jan reco")
        self.assertEqual(po.invoiced_amount, 500.0)
        self.assertEqual(po.recognized_amount, 800.0)
        self.assertTrue(po.is_over_recognized)
        res_over = self.env["perf.obligation"].search(
            [("is_over_recognized", "=", True)]
        )
        self.assertIn(po, res_over)
        res_not_over = self.env["perf.obligation"].search(
            [("is_over_recognized", "=", False)]
        )
        self.assertNotIn(po, res_not_over)

    def test_recognized_amount_and_is_over_recognized_expense(self):
        """Test recognized amount and over-recognized search for expense POs."""
        po = self._create_obligation(perf_type="expense", total_amount=1000)
        self._create_and_post_move(
            self.purchase_journal,
            [
                (self.payable_account, 0, 400, False),
                (self.exp_debit_bs, 400, 0, po),
            ],
            date="2026-01-01",
        )
        self.assertEqual(po.invoiced_amount, 400.0)
        self.assertEqual(po.recognized_amount, 0.0)
        self.assertFalse(po.is_over_recognized)
        # Recognize 600.0 (recognized > invoiced)
        po._recognize(600, "2026-01-31", "Jan reco")
        self.assertEqual(po.invoiced_amount, 400.0)
        self.assertEqual(po.recognized_amount, 600.0)
        self.assertTrue(po.is_over_recognized)
        res_over = self.env["perf.obligation"].search(
            [("is_over_recognized", "=", True)]
        )
        self.assertIn(po, res_over)

    def test_search_is_over_recognized_invalid_operator(self):
        """Unsupported search operators raise UserError."""
        with self.assertRaises(UserError):
            self.env["perf.obligation"]._search_is_over_recognized(">", True)

    def test_search_is_over_recognized_invalid_value(self):
        """Non-boolean search values raise UserError."""
        with self.assertRaises(UserError):
            self.env["perf.obligation"]._search_is_over_recognized("=", "invalid")
