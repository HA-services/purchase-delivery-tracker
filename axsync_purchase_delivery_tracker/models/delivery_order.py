# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
from datetime import timedelta

from odoo import api, fields, models

from .sql_utils import AVG, STATUS_SELECTION, order_query, refresh_views


class AxsyncDeliveryOrder(models.Model):
    """One row per confirmed purchase order. Read-only SQL view, nothing is stored."""
    _name = 'axsync.delivery.order'
    _description = 'AXSync Purchase Delivery Tracking'
    _auto = False
    _order = 'next_expected_date asc, id desc'
    _rec_name = 'order_id'

    order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Supplier', readonly=True)
    user_id = fields.Many2one('res.users', string='Buyer', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    date_order = fields.Datetime('Order Date', readonly=True)
    order_day = fields.Date('Order Day', readonly=True, help="Order date in the time zone of the company.")
    expected_day = fields.Date('Expected Day', readonly=True)
    next_expected_day = fields.Date('Next Expected Day', readonly=True,
                                    help="Earliest expected day of the lines that are still open.")
    last_receipt_day = fields.Date('Last Receipt Day', readonly=True)
    expected_date = fields.Datetime('Expected Delivery', readonly=True,
                                    help="Earliest expected date of all lines.")
    next_expected_date = fields.Datetime('Next Expected Delivery', readonly=True,
                                         help="Earliest expected date of the lines that are still open.")
    last_receipt_date = fields.Datetime('Last Receipt Date', readonly=True)
    status = fields.Selection(STATUS_SELECTION, string='Delivery Status', readonly=True)
    line_count = fields.Integer('Lines', readonly=True)
    open_line_count = fields.Integer('Open Lines', readonly=True)
    ordered_qty = fields.Float('Ordered (Product Unit)', readonly=True, digits='Product Unit of Measure')
    received_qty = fields.Float('Received (Product Unit)', readonly=True, digits='Product Unit of Measure')
    outstanding_qty = fields.Float('Outstanding (Product Unit)', readonly=True, digits='Product Unit of Measure',
                                   help="Quantity still expected on open lines, in the unit of each product.")
    received_pct = fields.Float('Received (%)', readonly=True, **AVG)
    delay_days = fields.Integer('Delay (Days)', readonly=True, **AVG,
                                help="Longest delay of any line. Completed lines count their real delay, "
                                     "open lines the days past their expected day.")
    is_open = fields.Boolean('Open', readonly=True)
    is_overdue = fields.Boolean('Overdue', readonly=True)
    is_completed = fields.Boolean('Completed', readonly=True)
    is_on_time = fields.Boolean('On Time', readonly=True)
    is_late = fields.Boolean('Late', readonly=True)
    order_count = fields.Integer('Orders', readonly=True, default=1)
    open_count = fields.Integer('Open Orders', readonly=True)
    overdue_count = fields.Integer('Overdue Orders', readonly=True)
    partial_count = fields.Integer('Partially Received Orders', readonly=True)
    completed_count = fields.Integer('Completed Orders', readonly=True)
    on_time_count = fields.Integer('On-Time Orders', readonly=True)
    late_count = fields.Integer('Late Orders', readonly=True)

    def init(self):
        self.env.cr.execute('DROP VIEW IF EXISTS %s CASCADE' % self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (SELECT a.*, 1 AS order_count FROM (%s) a)"
                            % (self._table, order_query()))

    def action_open_purchase_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'purchase.order',
                'res_id': self.order_id.id, 'views': [(False, 'form')]}

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @api.model
    def _aggregate(self, domain, fname, op='sum'):
        res = self.read_group(domain, ['%s:%s' % (fname, op)], [])
        return (res[0].get(fname) or 0.0) if res else 0.0

    @api.model
    def _dashboard_tiles(self, days):
        since = fields.Datetime.now() - timedelta(days=days) if days else False
        period = [('date_order', '>=', since)] if since else []
        done_period = [('is_completed', '=', True)] + (
            [('last_receipt_date', '>=', since)] if since else [])
        completed = self.search_count(done_period)
        on_time = self.search_count(done_period + [('is_on_time', '=', True)])
        avg_delay = self._aggregate(done_period, 'delay_days', 'avg')
        outstanding = self._aggregate([('is_open', '=', True)], 'outstanding_qty')
        label = 'Last %d days' % days if days else 'All time'
        order_model, line_model = 'axsync.delivery.order', 'axsync.delivery.line'
        return [
            {'key': 'total', 'label': 'Purchase orders', 'sub': label, 'value': self.search_count(period),
             'tone': 'primary', 'model': order_model, 'domain': period},
            {'key': 'pending', 'label': 'Pending deliveries', 'sub': 'Live', 'tone': 'info',
             'value': self.search_count([('status', '=', 'pending')]),
             'model': order_model, 'domain': [('status', '=', 'pending')]},
            {'key': 'partial', 'label': 'Partially received', 'sub': 'Live', 'tone': 'warning',
             'value': self.search_count([('status', '=', 'partial')]),
             'model': order_model, 'domain': [('status', '=', 'partial')]},
            {'key': 'overdue', 'label': 'Overdue orders', 'sub': 'Live', 'tone': 'danger',
             'value': self.search_count([('is_overdue', '=', True)]),
             'model': order_model, 'domain': [('is_overdue', '=', True)]},
            {'key': 'completed', 'label': 'Completed deliveries', 'sub': label, 'tone': 'success',
             'value': completed, 'model': order_model, 'domain': done_period},
            {'key': 'outstanding', 'label': 'Outstanding quantity', 'sub': 'Live, product units',
             'tone': 'secondary', 'value': round(outstanding, 2), 'model': line_model,
             'domain': [('is_open', '=', True), ('outstanding_qty', '>', 0)]},
            {'key': 'ontime', 'label': 'On-time delivery rate', 'sub': label, 'tone': 'success',
             'value': round(on_time * 100.0 / completed, 1) if completed else 0.0, 'suffix': ' %',
             'model': order_model, 'domain': done_period},
            {'key': 'delay', 'label': 'Average delay', 'sub': label, 'tone': 'warning',
             'value': round(avg_delay, 1), 'suffix': ' days', 'model': order_model, 'domain': done_period},
        ]

    @api.model
    def get_dashboard_data(self, days=90):
        refresh_views(self.env)
        days = int(days or 0)
        overdue = self.search([('is_overdue', '=', True)], order='delay_days desc, id', limit=8)
        ranking = self.env['axsync.delivery.supplier'].search(
            [('completed_orders', '>', 0)], order='rank asc, completed_orders desc', limit=8)
        return {
            'tiles': self._dashboard_tiles(days),
            'days': days,
            'overdue': [{'id': r.order_id.id, 'name': r.order_id.name, 'supplier': r.partner_id.display_name,
                         'expected': fields.Date.to_string(r.next_expected_day) if r.next_expected_day else '',
                         'delay': r.delay_days, 'status': dict(self._fields['status'].selection)[r.status]}
                        for r in overdue],
            'ranking': [{'id': r.partner_id.id, 'rank': r.rank, 'supplier': r.partner_id.display_name,
                         'on_time': round(r.on_time_pct, 1), 'avg_delay': round(r.avg_delay_days, 1),
                         'late': r.late_orders, 'completed': r.completed_orders} for r in ranking],
        }
