# Copyright 2026 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command

from odoo.addons.account_perf_obligation.tests.common import PerfObligationCommon


class TestPerfObligationSaleQtyDelivered(PerfObligationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {
                "name": "Standard Product",
                "perf_obligation_sale_auto_create": True,
                "perf_obligation_sale_recognition_method": "at_once",
            }
        )

    def _make_order(self, qty=10.0, price=100.0):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": qty,
                            "price_unit": price,
                        }
                    )
                ],
            }
        )

    def test_overdelivery_increases_obligation_total_amount(self):
        """Test that over-delivery increases total_amount proportionally,
        while partial delivery leaves it unchanged.
        """
        order = self._make_order(qty=10.0, price=100.0)
        order.action_confirm()
        line = order.order_line
        po = line.perf_obligation_id
        # 1. Standard initial total amount
        self.assertEqual(po.total_amount, 1000.0)
        # 2. Partial delivery (<= ordered qty) does not alter total_amount
        line.qty_delivered = 5.0
        self.assertEqual(po.total_amount, 1000.0)
        # 3. Exact delivery (= ordered qty) does not alter total_amount
        line.qty_delivered = 10.0
        self.assertEqual(po.total_amount, 1000.0)
        # 4. Over-delivery (> ordered qty) increases total_amount proportionally
        line.qty_delivered = 15.0
        self.assertEqual(po.total_amount, 1500.0)
        # 5. Reducing delivered qty back below ordered qty restores base total_amount
        line.qty_delivered = 8.0
        self.assertEqual(po.total_amount, 1000.0)
