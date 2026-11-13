# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
from odoo import fields, models

from .sql_utils import refresh_views


class ResPartner(models.Model):
    _inherit = 'res.partner'

    axsync_completed_orders = fields.Integer('Completed Orders', compute='_compute_axsync_delivery')
    axsync_late_orders = fields.Integer('Late Deliveries', compute='_compute_axsync_delivery')
    axsync_open_orders = fields.Integer('Open Orders', compute='_compute_axsync_delivery')
    axsync_overdue_orders = fields.Integer('Overdue Orders', compute='_compute_axsync_delivery')
    axsync_on_time_pct = fields.Float('On-Time (%)', compute='_compute_axsync_delivery')
    axsync_has_orders = fields.Boolean(compute='_compute_axsync_delivery')

    def _compute_axsync_delivery(self):
        """Supplier figures come from the reporting view, read once for all partners of the batch."""
        commercial = {p.id: p.commercial_partner_id.id or p.id for p in self if p.id}
        rows = {}
        if commercial and self.env.user.has_group('purchase.group_purchase_user'):
            refresh_views(self.env)
            for r in self.env['axsync.delivery.supplier'].search([('partner_id', 'in', list(set(commercial.values())))]):
                vals = rows.setdefault(r.partner_id.id, dict.fromkeys(
                    ['orders', 'completed', 'on_time', 'late', 'open', 'overdue'], 0))
                vals['orders'] += r.order_count
                vals['completed'] += r.completed_orders
                vals['on_time'] += r.on_time_orders
                vals['late'] += r.late_orders
                vals['open'] += r.open_orders
                vals['overdue'] += r.overdue_orders
        for partner in self:
            v = rows.get(commercial.get(partner.id))
            partner.axsync_has_orders = bool(v and v['orders'])
            partner.axsync_completed_orders = v['completed'] if v else 0
            partner.axsync_late_orders = v['late'] if v else 0
            partner.axsync_open_orders = v['open'] if v else 0
            partner.axsync_overdue_orders = v['overdue'] if v else 0
            partner.axsync_on_time_pct = round(v['on_time'] * 100.0 / v['completed'], 1) if v and v['completed'] else 0.0

    def _axsync_action_deliveries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Deliveries',
            'res_model': 'axsync.delivery.order',
            'view_mode': 'list,pivot,graph',
            'domain': [('partner_id', '=', self.commercial_partner_id.id)],
            'context': {'search_default_group_status': 1},
        }

    def action_axsync_view_deliveries(self):
        return self._axsync_action_deliveries()
