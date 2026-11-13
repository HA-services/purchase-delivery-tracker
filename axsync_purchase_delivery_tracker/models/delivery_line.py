# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
from odoo import fields, models

from .sql_utils import AVG, STATUS_SELECTION, line_query


class AxsyncDeliveryLine(models.Model):
    """One row per confirmed purchase order line. Read-only SQL view, nothing is stored."""
    _name = 'axsync.delivery.line'
    _description = 'AXSync Purchase Delivery Line'
    _auto = False
    _order = 'expected_date asc, id desc'
    _rec_name = 'order_id'

    line_id = fields.Many2one('purchase.order.line', string='Order Line', readonly=True)
    order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Supplier', readonly=True)
    user_id = fields.Many2one('res.users', string='Buyer', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unit', readonly=True)
    date_order = fields.Datetime('Order Date', readonly=True)
    order_day = fields.Date('Order Day', readonly=True, help="Order date in the time zone of the company.")
    expected_day = fields.Date('Expected Day', readonly=True, help="Expected delivery day in the time zone of the company.")
    receipt_day = fields.Date('Last Receipt Day', readonly=True, help="Day of the last receipt in the time zone of the company.")
    expected_date = fields.Datetime('Expected Delivery', readonly=True)
    receipt_date = fields.Datetime('Last Receipt Date', readonly=True,
                                   help="Date of the last validated receipt of this line. Returns are ignored.")
    ordered_qty = fields.Float('Ordered', readonly=True, digits='Product Unit of Measure',
                               help="Ordered quantity in the unit of the purchase order line.")
    received_qty = fields.Float('Received', readonly=True, digits='Product Unit of Measure',
                                help="Quantity received in the unit of the purchase order line. Validated "
                                     "returns to the supplier are already subtracted by Odoo.")
    remaining_qty = fields.Float('Remaining', readonly=True, digits='Product Unit of Measure',
                                 help="Ordered minus received quantity, never below zero, in the line unit.")
    outstanding_qty = fields.Float('Outstanding (Product Unit)', readonly=True, digits='Product Unit of Measure',
                                   help="Quantity still expected on open lines, converted to the unit of the product. "
                                        "Safe to add up across lines.")
    status = fields.Selection(STATUS_SELECTION, string='Delivery Status', readonly=True)
    is_open = fields.Boolean('Open', readonly=True)
    is_overdue = fields.Boolean('Overdue', readonly=True,
                                help="Still open and the expected delivery day is before today.")
    is_completed = fields.Boolean('Completed', readonly=True)
    is_on_time = fields.Boolean('On Time', readonly=True,
                                help="Completed and the last receipt was on or before the expected day.")
    is_late = fields.Boolean('Late', readonly=True)
    delay_days = fields.Integer('Delay (Days)', readonly=True, **AVG,
                                help="Completed lines: days between the expected day and the last receipt. "
                                     "Open lines: days past the expected day. Never negative.")
    delay_bucket = fields.Selection([
        ('d1', '1 to 7 days'), ('d2', '8 to 14 days'), ('d3', '15 to 30 days'), ('d4', 'Over 30 days')],
        string='Overdue Age', readonly=True)
    overdue_count = fields.Integer('Overdue Lines', readonly=True)
    completed_count = fields.Integer('Completed Lines', readonly=True)
    on_time_count = fields.Integer('On-Time Lines', readonly=True)
    late_count = fields.Integer('Late Lines', readonly=True)

    def init(self):
        self.env.cr.execute('DROP VIEW IF EXISTS %s CASCADE' % self._table)
        self.env.cr.execute('CREATE OR REPLACE VIEW %s AS (%s)' % (self._table, line_query()))

    def action_open_purchase_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'purchase.order',
                'res_id': self.order_id.id, 'views': [(False, 'form')]}
