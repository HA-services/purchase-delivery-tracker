# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
from odoo import fields, models

from .sql_utils import AVG, supplier_query


class AxsyncDeliverySupplier(models.Model):
    """One row per supplier and company with delivery performance. Read-only SQL view."""
    _name = 'axsync.delivery.supplier'
    _description = 'AXSync Supplier Delivery Performance'
    _auto = False
    _order = 'company_id, rank asc, completed_orders desc, id'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner', string='Supplier', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    rank = fields.Integer('Rank', readonly=True,
                          help="Position among the suppliers of the company with at least one completed order: "
                               "highest on-time percentage first, then lowest average delay.")
    order_count = fields.Integer('Confirmed Orders', readonly=True)
    completed_orders = fields.Integer('Completed Orders', readonly=True)
    on_time_orders = fields.Integer('On-Time Orders', readonly=True)
    late_orders = fields.Integer('Late Deliveries', readonly=True)
    open_orders = fields.Integer('Open Orders', readonly=True)
    overdue_orders = fields.Integer('Overdue Orders', readonly=True)
    partial_orders = fields.Integer('Partially Received', readonly=True)
    outstanding_qty = fields.Float('Outstanding (Product Unit)', readonly=True, digits='Product Unit of Measure')
    on_time_pct = fields.Float('On-Time (%)', readonly=True, **AVG,
                               help="On-time completed orders divided by completed orders. An order is on time "
                                    "when every line was last received on or before its expected day.")
    avg_delay_days = fields.Float('Average Delay (Days)', readonly=True, **AVG,
                                  help="Average delay of completed orders. On-time orders count as zero.")
    avg_late_days = fields.Float('Average Days Late', readonly=True, **AVG,
                                 help="Average delay of the late orders only.")
    max_delay_days = fields.Integer('Worst Delay (Days)', readonly=True, **AVG)

    def init(self):
        self.env.cr.execute('DROP VIEW IF EXISTS %s CASCADE' % self._table)
        self.env.cr.execute('CREATE OR REPLACE VIEW %s AS (%s)' % (self._table, supplier_query()))

    def action_view_orders(self):
        self.ensure_one()
        return self.partner_id._axsync_action_deliveries()
