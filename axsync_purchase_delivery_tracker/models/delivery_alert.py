# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .sql_utils import refresh_views

_logger = logging.getLogger(__name__)

PARAM = 'axsync_purchase_delivery_tracker.'


class AxsyncDeliveryAlert(models.Model):
    """Log of the delivery alerts already sent. The unique key prevents duplicates."""
    _name = 'axsync.delivery.alert'
    _description = 'AXSync Delivery Alert'
    _order = 'create_date desc, id desc'
    _rec_name = 'order_id'

    order_id = fields.Many2one('purchase.order', string='Purchase Order', required=True,
                               ondelete='cascade', index=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Company', related='order_id.company_id',
                                 store=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Supplier', related='order_id.partner_id', store=True)
    alert_type = fields.Selection([
        ('upcoming', 'Upcoming Delivery'),
        ('overdue', 'Overdue Delivery'),
        ('partial', 'Partially Received'),
    ], string='Alert Type', required=True, readonly=True)
    alert_key = fields.Char('Trigger', required=True, readonly=True,
                            help="Identifies the situation that triggered the alert. The same alert type is "
                                 "sent only once for the same trigger.")
    user_id = fields.Many2one('res.users', string='Notified User', readonly=True)
    summary = fields.Char('Message', readonly=True)

    _sql_constraints = [
        ('axsync_alert_unique', 'unique(order_id, alert_type, alert_key)',
         'This alert was already sent for this purchase order.'),
    ]

    # ------------------------------------------------------------------
    @api.model
    def _get_settings(self):
        icp = self.env['ir.config_parameter']
        typed = hasattr(icp, 'get_bool')  # Odoo 20 replaced get_param by typed getters

        def flag(name):
            if typed:
                return icp.get_bool(PARAM + name, True)
            return icp.get_param(PARAM + name, 'True') in ('True', 'true', '1')

        try:
            days = icp.get_int(PARAM + 'alert_days', 3) if typed else int(icp.get_param(PARAM + 'alert_days', '3'))
        except ValueError:
            days = 3
        return {'upcoming': flag('alert_upcoming'), 'overdue': flag('alert_overdue'),
                'partial': flag('alert_partial'), 'days': max(days, 0)}

    @api.model
    def _recipient(self, order):
        """The buyer of the order, or the user who created it. Never the system user."""
        user = order.user_id or order.create_uid
        if user and user.active and user.id != self.env.ref('base.user_root').id and user.share is False:
            return user
        return self.env['res.users']

    @api.model
    def _candidates(self, settings):
        """Return [(delivery.order record, alert type, key, message)]."""
        Order = self.env['axsync.delivery.order']
        today = fields.Date.context_today(self)
        res = []
        if settings['upcoming']:
            limit = today + timedelta(days=settings['days'])
            for o in Order.search([('is_open', '=', True), ('is_overdue', '=', False),
                                   ('next_expected_day', '<=', limit)]):
                day = o.next_expected_day
                res.append((o, 'upcoming', str(day),
                            _("%(po)s from %(supplier)s is expected on %(date)s.",
                              po=o.order_id.name, supplier=o.partner_id.display_name, date=day)))
        if settings['overdue']:
            for o in Order.search([('is_overdue', '=', True)]):
                day = o.next_expected_day
                res.append((o, 'overdue', str(day),
                            _("%(po)s from %(supplier)s is overdue by %(days)s days. Outstanding quantity: %(qty)s.",
                              po=o.order_id.name, supplier=o.partner_id.display_name,
                              days=o.delay_days, qty=round(o.outstanding_qty, 2))))
        if settings['partial']:
            for o in Order.search([('status', '=', 'partial')]):
                key = '%s|%s' % (o.last_receipt_date, round(o.outstanding_qty, 4))
                res.append((o, 'partial', key,
                            _("%(po)s from %(supplier)s is partially received. Outstanding quantity: %(qty)s.",
                              po=o.order_id.name, supplier=o.partner_id.display_name,
                              qty=round(o.outstanding_qty, 2))))
        return res

    @api.model
    def cron_send_alerts(self):
        """Create one to-do activity per new alert for the buyer. Safe to run any number of times."""
        refresh_views(self.env)
        settings = self._get_settings()
        candidates = self._candidates(settings)
        if not candidates:
            return 0
        existing = set()
        for alert in self.search([('order_id', 'in', [c[0].order_id.id for c in candidates])]):
            existing.add((alert.order_id.id, alert.alert_type, alert.alert_key))
        created = 0
        today = fields.Date.context_today(self)
        for row, alert_type, key, message in candidates:
            order = row.order_id
            if (order.id, alert_type, key) in existing:
                continue
            user = self._recipient(order)
            if not user:
                continue  # no human recipient yet: try again on the next run
            try:
                order.activity_schedule(
                    'mail.mail_activity_data_todo', date_deadline=today,
                    summary=dict(self._fields['alert_type'].selection)[alert_type],
                    note=message, user_id=user.id)
            except AccessError:
                _logger.info("Delivery alert for %s skipped: %s cannot access the order.", order.name, user.login)
                continue
            self.create({'order_id': order.id, 'alert_type': alert_type, 'alert_key': key,
                         'user_id': user.id, 'summary': message})
            existing.add((order.id, alert_type, key))
            created += 1
        _logger.info("AXSync delivery alerts: %s new alert(s).", created)
        return created
