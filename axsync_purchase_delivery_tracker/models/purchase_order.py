# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models

from .sql_utils import STATUS_SELECTION, refresh_views


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    axsync_delivery_line_ids = fields.One2many('axsync.delivery.line', 'order_id', string='Delivery Tracking',
                                               readonly=True)
    axsync_delivery_status = fields.Selection(STATUS_SELECTION, string='Delivery Status',
                                              compute='_compute_axsync_delivery')
    axsync_expected_date = fields.Date('Next Expected Delivery', compute='_compute_axsync_delivery')
    axsync_last_receipt_date = fields.Date('Last Receipt Date', compute='_compute_axsync_delivery')
    axsync_delay_days = fields.Integer('Delay (Days)', compute='_compute_axsync_delivery')
    axsync_is_overdue = fields.Boolean('Overdue', compute='_compute_axsync_delivery')
    axsync_outstanding_qty = fields.Float('Outstanding Quantity', compute='_compute_axsync_delivery',
                                          digits='Product Unit of Measure')
    axsync_received_pct = fields.Float('Received (%)', compute='_compute_axsync_delivery')

    @api.depends('state', 'order_line.qty_received', 'order_line.product_qty', 'order_line.date_planned',
                 'picking_ids.state')
    def _compute_axsync_delivery(self):
        ids = [o._origin.id for o in self if o._origin.id]
        rows = {}
        if ids:
            refresh_views(self.env)
            rows = {r.order_id.id: r for r in self.env['axsync.delivery.order'].search([('order_id', 'in', ids)])}
        for order in self:
            row = rows.get(order._origin.id)
            order.axsync_delivery_status = row.status if row else False
            order.axsync_expected_date = (row.next_expected_day or row.expected_day) if row else False
            order.axsync_last_receipt_date = row.last_receipt_day if row else False
            order.axsync_delay_days = row.delay_days if row else 0
            order.axsync_is_overdue = row.is_overdue if row else False
            order.axsync_outstanding_qty = row.outstanding_qty if row else 0.0
            order.axsync_received_pct = row.received_pct if row else 0.0
