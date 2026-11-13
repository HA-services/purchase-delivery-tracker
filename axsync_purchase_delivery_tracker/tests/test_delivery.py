# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import Form, TransactionCase, tagged

# Version specific names, adapted when the module is ported.
PRODUCT_VALS = {'type': 'consu', 'is_storable': True}
GROUPS = 'groups_id'
UOM = 'product_uom'


@tagged('post_install', '-at_install', 'axsync_delivery')
class TestAxsyncDelivery(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.unit = env.ref('uom.product_uom_unit')
        cls.dozen = env.ref('uom.product_uom_dozen')
        cls.vendor_a = env['res.partner'].create({'name': 'AX Vendor A'})
        cls.vendor_b = env['res.partner'].create({'name': 'AX Vendor B'})
        cls.product = env['product.product'].create(dict({'name': 'AX Widget'}, **PRODUCT_VALS))
        cls.product2 = env['product.product'].create(dict({'name': 'AX Gadget'}, **PRODUCT_VALS))
        cls.service = env['product.product'].create({'name': 'AX Service', 'type': 'service'})
        cls.buyer = env['res.users'].create({
            'name': 'AX Buyer', 'login': 'ax_buyer', 'email': 'ax_buyer@example.com',
            GROUPS: [Command.set([env.ref('base.group_user').id, env.ref('purchase.group_purchase_user').id,
                                  env.ref('stock.group_stock_user').id])],
        })

    # ------------------------------------------------------------------ helpers
    def _set_param(self, name, value):
        icp = self.env['ir.config_parameter']
        key = 'axsync_purchase_delivery_tracker.' + name
        if hasattr(icp, 'set_bool'):  # Odoo 20 typed setters
            (icp.set_int if name == 'alert_days' else icp.set_bool)(key, int(value) if name == 'alert_days' else value == 'True')
        else:
            icp.set_param(key, value)

    def _po(self, partner=None, lines=None, confirm=True, company=None, **kw):
        """lines: list of (product, qty, days_from_today[, uom])."""
        env = self.env if not company else self.env(context=dict(self.env.context, allowed_company_ids=[company.id]))
        lines = lines or [(self.product, 10.0, 5)]
        order_lines = []
        for spec in lines:
            product, qty, days = spec[:3]
            vals = {'product_id': product.id, 'product_qty': qty, 'price_unit': 10.0,
                    'name': product.name,
                    'date_planned': fields.Datetime.now() + timedelta(days=days)}
            if len(spec) > 3:
                vals[UOM] = spec[3].id
            order_lines.append(Command.create(vals))
        vals = dict({'partner_id': (partner or self.vendor_a).id, 'order_line': order_lines}, **kw)
        if company:
            vals['company_id'] = company.id
        po = env['purchase.order'].create(vals)
        if confirm:
            po.button_confirm()
        return po

    def _receive(self, po, qty=None, backorder=True, per_line=None):
        """Validate the open receipt of the order. qty: quantity to receive on every move (None = demand)."""
        picking = po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))[:1]
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = qty if qty is not None else move.product_uom_qty
            move.picked = True
        ctx = {'skip_backorder': True}
        if not backorder:
            ctx['picking_ids_not_to_backorder'] = picking.ids
        picking.with_context(**ctx).button_validate()
        return picking

    def _return(self, picking, qty):
        wiz = Form(self.env['stock.return.picking'].with_context(
            active_ids=picking.ids, active_id=picking.id, active_model='stock.picking')).save()
        wiz.product_return_moves.quantity = qty
        res = wiz.action_create_returns() if hasattr(wiz, 'action_create_returns') else wiz.create_returns()
        ret = self.env['stock.picking'].browse(res['res_id'])
        for move in ret.move_ids:
            move.quantity = qty
            move.picked = True
        ret.with_context(skip_backorder=True).button_validate()
        return ret

    def _line(self, po, product=None):
        self.env.flush_all()
        self.env.invalidate_all()
        rows = self.env['axsync.delivery.line'].search([('order_id', '=', po.id)])
        return rows.filtered(lambda r: r.product_id == (product or self.product)) if product or len(rows) > 1 else rows

    def _order(self, po):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env['axsync.delivery.order'].search([('order_id', '=', po.id)])

    def _supplier(self, partner, company=None):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env['axsync.delivery.supplier'].search(
            [('partner_id', '=', partner.id), ('company_id', '=', (company or self.company).id)])

    # ------------------------------------------------------------------ tests
    def test_01_installation(self):
        for model in ('axsync.delivery.line', 'axsync.delivery.order', 'axsync.delivery.supplier',
                      'axsync.delivery.alert'):
            self.assertIn(model, self.env)
            self.env[model].search([], limit=1)
        self.assertTrue(self.env.ref('axsync_purchase_delivery_tracker.axsync_delivery_alert_cron'))
        self.assertTrue(self.env.ref('axsync_purchase_delivery_tracker.axsync_delivery_dashboard_action'))
        # every shipped view and the settings page compile
        self.env['res.config.settings'].get_views([(False, 'form')])
        for action_xml in ('axsync_delivery_line_action', 'axsync_delivery_order_action',
                           'axsync_delivery_supplier_action', 'axsync_delivery_alert_action'):
            action = self.env.ref('axsync_purchase_delivery_tracker.' + action_xml)
            self.env[action.res_model].get_views([(False, 'list'), (False, 'form'), (False, 'search'),
                                                  (False, 'pivot'), (False, 'graph')])
        self.env['res.partner'].get_views([(False, 'form')])
        # the daily cron and the settings button run the same routine
        cron = self.env.ref('axsync_purchase_delivery_tracker.axsync_delivery_alert_cron')
        cron.method_direct_trigger()
        self.env['res.config.settings'].create({}).action_axsync_send_alerts()

    def test_02_confirmation_and_pending(self):
        draft = self._po(confirm=False)
        self.assertFalse(self._line(draft), "Draft orders are not tracked")
        po = self._po(lines=[(self.product, 10.0, 5), (self.service, 1.0, 5)])
        line = self._line(po)
        self.assertEqual(len(line), 1, "Service lines never create receipts")
        self.assertEqual(line.status, 'pending')
        self.assertEqual(line.ordered_qty, 10.0)
        self.assertEqual(line.received_qty, 0.0)
        self.assertEqual(line.remaining_qty, 10.0)
        self.assertEqual(line.outstanding_qty, 10.0)
        self.assertFalse(line.receipt_date)
        self.assertTrue(line.is_open)
        self.assertFalse(line.is_overdue)
        self.assertEqual(line.delay_days, 0)
        self.assertEqual(line.expected_date, po.order_line.filtered(lambda l: l.product_id == self.product).date_planned)
        self.assertEqual(line.expected_day, line.expected_date.date())  # company time zone is UTC here
        order = self._order(po)
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.outstanding_qty, 10.0)

    def test_03_partial_then_full_receipt(self):
        po = self._po(lines=[(self.product, 10.0, 5)])
        self._receive(po, qty=4.0)
        line, order = self._line(po), self._order(po)
        self.assertEqual(line.status, 'partial')
        self.assertEqual(line.received_qty, 4.0)
        self.assertEqual(line.remaining_qty, 6.0)
        self.assertEqual(line.outstanding_qty, 6.0)
        self.assertTrue(line.receipt_date)
        self.assertEqual(order.status, 'partial')
        self.assertEqual(order.received_pct, 40.0)
        self._receive(po)  # backorder with the remaining 6
        line, order = self._line(po), self._order(po)
        self.assertEqual(line.status, 'received')
        self.assertEqual(line.received_qty, 10.0)
        self.assertEqual(line.remaining_qty, 0.0)
        self.assertEqual(line.outstanding_qty, 0.0)
        self.assertTrue(line.is_completed)
        self.assertTrue(line.is_on_time)
        self.assertEqual(line.delay_days, 0)
        self.assertEqual(order.status, 'received')
        self.assertTrue(order.is_completed and order.is_on_time)
        self.assertFalse(order.is_open)

    def test_04_multiple_receipts_use_last_receipt_date(self):
        po = self._po(lines=[(self.product, 9.0, 5)])
        self._receive(po, qty=3.0)
        self._receive(po, qty=3.0)
        self.assertEqual(self._line(po).status, 'partial')
        self._receive(po)
        line = self._line(po)
        self.assertEqual(line.status, 'received')
        last = max(po.picking_ids.move_ids.filtered(lambda m: m.state == 'done').mapped('date'))
        self.assertEqual(line.receipt_date, last)
        self.assertEqual(len(po.picking_ids), 3)

    def test_05_overdue_open_order(self):
        po = self._po(lines=[(self.product, 10.0, -4), (self.product2, 5.0, 10)])
        order = self._order(po)
        self.assertTrue(order.is_overdue)
        self.assertEqual(order.delay_days, 4)
        line = self._line(po, self.product)
        self.assertTrue(line.is_overdue)
        self.assertEqual(line.delay_days, 4)
        self.assertEqual(line.delay_bucket, 'd1')
        self.assertFalse(self._line(po, self.product2).is_overdue)
        # a partial receipt does not stop the order from being overdue
        self._receive(po, qty=2.0)
        self.assertTrue(self._order(po).is_overdue)
        self.assertEqual(self._order(po).status, 'partial')

    def test_06_late_receipt(self):
        po = self._po(lines=[(self.product, 10.0, -6)])
        self._receive(po)
        line, order = self._line(po), self._order(po)
        self.assertEqual(line.status, 'received')
        self.assertTrue(line.is_late)
        self.assertFalse(line.is_overdue, "A delivered line is no longer overdue")
        self.assertEqual(line.delay_days, 6)
        self.assertTrue(order.is_late)
        self.assertEqual(order.delay_days, 6)
        self.assertFalse(order.is_on_time)

    def test_07_return_reduces_received_quantity(self):
        po = self._po(lines=[(self.product, 10.0, 5)])
        picking = self._receive(po)
        self.assertEqual(self._line(po).status, 'received')
        self._return(picking, 4.0)
        line = self._line(po)
        self.assertEqual(line.received_qty, 6.0)
        self.assertEqual(line.remaining_qty, 4.0)
        self.assertEqual(line.status, 'partial')
        self.assertEqual(line.outstanding_qty, 4.0)
        self.assertEqual(self._order(po).status, 'partial')
        self.assertTrue(self._line(po).is_open, "After a return a replacement is expected")

    def test_08_uom_conversion(self):
        po = self._po(lines=[(self.product, 2.0, 5, self.dozen)])  # 2 dozen = 24 units
        line = self._line(po)
        self.assertEqual(line.ordered_qty, 2.0)
        self.assertEqual(line.uom_id, self.dozen)
        self.assertEqual(line.outstanding_qty, 24.0)
        self._receive(po, qty=12.0)  # the receipt is in units of the move (product unit): 12 units = 1 dozen
        line = self._line(po)
        self.assertAlmostEqual(line.received_qty, 1.0, places=4)
        self.assertAlmostEqual(line.remaining_qty, 1.0, places=4)
        self.assertAlmostEqual(line.outstanding_qty, 12.0, places=3)
        self.assertEqual(line.status, 'partial')
        self.assertAlmostEqual(self._order(po).outstanding_qty, 12.0, places=3)

    def test_09_closed_short_without_backorder(self):
        po = self._po(lines=[(self.product, 10.0, 5)])
        self._receive(po, qty=7.0, backorder=False)
        line, order = self._line(po), self._order(po)
        self.assertEqual(line.status, 'closed')
        self.assertEqual(line.received_qty, 7.0)
        self.assertEqual(line.remaining_qty, 3.0)
        self.assertEqual(line.outstanding_qty, 0.0)
        self.assertFalse(line.is_open)
        self.assertTrue(line.is_completed)
        self.assertEqual(order.status, 'closed')
        self.assertFalse(order.is_overdue)

    def test_10_supplier_performance_and_ranking(self):
        # Vendor A: one on-time and one late order. Vendor B: two on-time orders.
        po1 = self._po(self.vendor_a, [(self.product, 5.0, 3)])
        po2 = self._po(self.vendor_a, [(self.product, 5.0, -4)])
        po3 = self._po(self.vendor_a, [(self.product, 5.0, -9)])  # stays open and overdue
        po4 = self._po(self.vendor_b, [(self.product, 5.0, 2)])
        po5 = self._po(self.vendor_b, [(self.product2, 5.0, 2)])
        for po in (po1, po2, po4, po5):
            self._receive(po)
        a, b = self._supplier(self.vendor_a), self._supplier(self.vendor_b)
        self.assertEqual((a.order_count, a.completed_orders, a.on_time_orders, a.late_orders), (3, 2, 1, 1))
        self.assertEqual(a.on_time_pct, 50.0)
        self.assertEqual(a.avg_delay_days, 2.0)  # (0 + 4) / 2
        self.assertEqual(a.avg_late_days, 4.0)
        self.assertEqual(a.max_delay_days, 4)
        self.assertEqual((a.open_orders, a.overdue_orders), (1, 1))
        self.assertEqual((b.completed_orders, b.on_time_orders, b.late_orders), (2, 2, 0))
        self.assertEqual(b.on_time_pct, 100.0)
        self.assertEqual(b.avg_delay_days, 0.0)
        self.assertLess(b.rank, a.rank)
        self.assertEqual(b.rank, 1)
        self.assertEqual(po3.state, 'purchase')

    def test_11_multi_company_access(self):
        company2 = self.env['res.company'].create({'name': 'AX Second Company'})
        user = self.env['res.users'].create({
            'name': 'AX Limited Buyer', 'login': 'ax_limited', 'company_id': self.company.id,
            'company_ids': [Command.set([self.company.id])],
            GROUPS: [Command.set([self.env.ref('base.group_user').id,
                                  self.env.ref('purchase.group_purchase_user').id])],
        })
        po1 = self._po()
        po2 = self._po(company=company2)
        self.assertEqual(po2.company_id, company2)
        self.env.flush_all()
        for model, field in (('axsync.delivery.line', 'order_id'), ('axsync.delivery.order', 'order_id')):
            seen = self.env[model].with_user(user).search([]).mapped(field)
            self.assertIn(po1, seen)
            self.assertNotIn(po2, seen)
            admin_seen = self.env[model].with_context(allowed_company_ids=[self.company.id, company2.id]).search([]).mapped(field)
            self.assertIn(po2, admin_seen)
        suppliers = self.env['axsync.delivery.supplier'].with_user(user).search([])
        self.assertTrue(suppliers)
        self.assertNotIn(company2, suppliers.mapped('company_id'))
        # users without Purchase rights cannot read the reports
        nobody = self.env['res.users'].create({
            'name': 'AX Nobody', 'login': 'ax_nobody',
            GROUPS: [Command.set([self.env.ref('base.group_user').id])]})
        with self.assertRaises(AccessError):
            self.env['axsync.delivery.order'].with_user(nobody).search([])

    def test_12_alerts_are_sent_once(self):
        Alert = self.env['axsync.delivery.alert']
        self._set_param('alert_days', '3')
        po_up = self._po(lines=[(self.product, 5.0, 2)], user_id=self.buyer.id)
        po_over = self._po(lines=[(self.product, 5.0, -3)], user_id=self.buyer.id)
        po_part = self._po(lines=[(self.product, 10.0, 20)], user_id=self.buyer.id)
        self._receive(po_part, qty=4.0)
        po_far = self._po(lines=[(self.product, 5.0, 30)], user_id=self.buyer.id)
        self.env.flush_all()
        created = Alert.cron_send_alerts()
        kinds = {(a.order_id.id, a.alert_type) for a in Alert.search([])}
        self.assertIn((po_up.id, 'upcoming'), kinds)
        self.assertIn((po_over.id, 'overdue'), kinds)
        self.assertIn((po_part.id, 'partial'), kinds)
        self.assertNotIn((po_far.id, 'upcoming'), kinds)
        self.assertNotIn((po_up.id, 'overdue'), kinds)
        self.assertEqual(created, len(Alert.search([])))
        activities = self.env['mail.activity'].search([('res_model', '=', 'purchase.order'),
                                                      ('res_id', 'in', (po_up + po_over + po_part).ids)])
        self.assertEqual(activities.mapped('user_id'), self.buyer)
        count_alerts, count_acts = Alert.search_count([]), len(activities)
        # running again does not notify again
        self.assertEqual(Alert.cron_send_alerts(), 0)
        self.assertEqual(Alert.search_count([]), count_alerts)
        self.assertEqual(self.env['mail.activity'].search_count(
            [('res_model', '=', 'purchase.order'), ('res_id', 'in', (po_up + po_over + po_part).ids)]), count_acts)
        # a new partial receipt is a new situation and is notified once
        self._receive(po_part, qty=3.0)
        self.assertEqual(Alert.cron_send_alerts(), 1)
        self.assertEqual(Alert.cron_send_alerts(), 0)

    def test_13_alert_settings_and_recipient(self):
        Alert = self.env['axsync.delivery.alert']
        self._set_param('alert_overdue', 'False')
        po = self._po(lines=[(self.product, 5.0, -3)], user_id=self.buyer.id)
        Alert.cron_send_alerts()
        self.assertFalse(Alert.search([('order_id', '=', po.id), ('alert_type', '=', 'overdue')]))
        self._set_param('alert_overdue', 'True')
        # no human recipient: nothing is created and the alert stays possible
        po.user_id = False
        po.create_uid = self.env.ref('base.user_root')
        self.env.flush_all()
        Alert.cron_send_alerts()
        self.assertFalse(Alert.search([('order_id', '=', po.id)]))
        po.user_id = self.buyer
        Alert.cron_send_alerts()
        self.assertTrue(Alert.search([('order_id', '=', po.id), ('alert_type', '=', 'overdue')]))

    def test_14_purchase_order_and_partner_integration(self):
        po = self._po(lines=[(self.product, 10.0, -2)])
        self._receive(po, qty=4.0)
        self.env.invalidate_all()
        self.assertEqual(po.axsync_delivery_status, 'partial')
        self.assertTrue(po.axsync_is_overdue)
        self.assertEqual(po.axsync_delay_days, 2)
        self.assertEqual(po.axsync_outstanding_qty, 6.0)
        self.assertEqual(po.axsync_received_pct, 40.0)
        self.assertEqual(len(po.axsync_delivery_line_ids), 1)
        draft = self._po(confirm=False)
        self.assertFalse(draft.axsync_delivery_status)
        # the same field values are served for a whole batch of orders
        batch = po + self._po() + draft
        self.assertEqual(len(batch.mapped('axsync_delivery_status')), 3)
        # the order form and list views render the new fields
        self.env['purchase.order'].get_views([(False, 'form'), (False, 'list')])
        po2 = self._po(self.vendor_b, [(self.product, 5.0, 3)])
        self._receive(po2)
        self.env.invalidate_all()
        self.assertEqual(self.vendor_b.axsync_completed_orders, 1)
        self.assertEqual(self.vendor_b.axsync_on_time_pct, 100.0)
        self.assertTrue(self.vendor_b.axsync_has_orders)
        action = self.vendor_b.action_axsync_view_deliveries()
        self.assertEqual(self.env['axsync.delivery.order'].search(action['domain'], limit=5).mapped('partner_id'),
                         self.vendor_b)

    def test_15_dashboard(self):
        base = self.env['axsync.delivery.order'].get_dashboard_data(90)
        tiles0 = {t['key']: t['value'] for t in base['tiles']}
        self._po(lines=[(self.product, 10.0, 5)])                      # pending
        po_part = self._po(lines=[(self.product, 10.0, 5)])
        self._receive(po_part, qty=5.0)                                # partial
        self._po(lines=[(self.product, 10.0, -3)])                     # overdue + pending
        po_done = self._po(lines=[(self.product, 6.0, 4)])
        self._receive(po_done)                                          # completed on time
        po_late = self._po(lines=[(self.product, 6.0, -2)])
        self._receive(po_late)                                          # completed late
        self.env.flush_all()
        data = self.env['axsync.delivery.order'].get_dashboard_data(90)
        tiles = {t['key']: t['value'] for t in data['tiles']}
        self.assertEqual(tiles['total'] - tiles0['total'], 5)
        self.assertEqual(tiles['pending'] - tiles0['pending'], 2)
        self.assertEqual(tiles['partial'] - tiles0['partial'], 1)
        self.assertEqual(tiles['overdue'] - tiles0['overdue'], 1)
        self.assertEqual(tiles['completed'] - tiles0['completed'], 2)
        self.assertEqual(tiles['outstanding'] - tiles0['outstanding'], 10 + 5 + 10)
        self.assertTrue(data['overdue'] and data['ranking'])
        # every tile carries a domain that the target model accepts
        for tile in data['tiles']:
            self.env[tile['model']].search_count(tile['domain'])
        self.assertTrue(self.env['axsync.delivery.order'].get_dashboard_data(0)['tiles'])

    def test_16_reports_and_export(self):
        po = self._po(lines=[(self.product, 10.0, -5)])
        self.env.flush_all()
        for model in ('axsync.delivery.line', 'axsync.delivery.order', 'axsync.delivery.supplier'):
            Model = self.env[model]
            res = Model.search([], limit=3).export_data(['partner_id', 'status'] if model != 'axsync.delivery.supplier' else ['partner_id', 'on_time_pct'])
            self.assertTrue(res['datas'])
            # pivot, graph and list groupings used by the shipped views
            Model.read_group([], ['partner_id'], ['partner_id'])
        # overdue analysis buckets
        grouped = self.env['axsync.delivery.line'].read_group(
            [('is_overdue', '=', True)], ['overdue_count:sum'], ['delay_bucket'])
        self.assertTrue(any(g['delay_bucket'] == 'd1' for g in grouped))
        for action_xml in ('axsync_delivery_line_action', 'axsync_delivery_order_action',
                           'axsync_delivery_supplier_action', 'axsync_delivery_overdue_action',
                           'axsync_delivery_alert_action'):
            action = self.env.ref('axsync_purchase_delivery_tracker.' + action_xml)
            self.env[action.res_model].search(
                eval(action.domain or '[]'), limit=1)
        self.assertTrue(po)
