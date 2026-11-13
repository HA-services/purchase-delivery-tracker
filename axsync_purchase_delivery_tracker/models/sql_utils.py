# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
"""SQL building blocks shared by the three read-only reporting views.

Every view embeds the queries below as sub-selects, so a view never depends on
another view and the creation order of the models does not matter.

Calculation rules (all documented in the README):

* Only confirmed purchase orders (state purchase or done) and only stockable /
  consumable lines (service lines never create receipts) are tracked.
* Received quantity is the native ``purchase.order.line.qty_received``. Odoo
  computes it from validated stock moves, converts units of measure and
  subtracts validated returns to the supplier.
* Receipt date is the date of the last validated receipt move of the line.
  Returns to the supplier are ignored for the date.
* A line that is not fully received, has no open receipt move left (backorder
  cancelled or validated without backorder) and has no validated return is
  "closed short". After a return the line stays open: a replacement is expected.
* Dates are compared as calendar days in the time zone of the company partner
  (UTC when it has none).
"""

# Name of the unit of measure column on purchase_order_line.
UOM_COLUMN = 'product_uom'

# Keyword used by fields that must be averaged when grouped.
AVG = {'aggregator': 'avg'}

EPS = '0.000001'

STATUS_SELECTION = [
    ('pending', 'Pending'),
    ('partial', 'Partially Received'),
    ('received', 'Fully Received'),
    ('closed', 'Closed Short'),
]


def line_query():
    """One row per tracked purchase order line."""
    return """
    SELECT f.id, f.line_id, f.order_id, f.company_id, f.partner_id, f.user_id, f.date_order, f.order_day,
           f.product_id, f.uom_id, f.expected_date, f.receipt_date, f.expected_day, f.receipt_day,
           f.ordered_qty, f.received_qty, f.ordered_base, f.received_base,
           GREATEST(f.ordered_qty - f.received_qty, 0.0) AS remaining_qty,
           f.status, f.is_open, f.is_overdue, f.is_completed,
           f.delay_days, f.outstanding_qty,
           (f.is_completed AND f.delay_days = 0) AS is_on_time,
           (f.is_completed AND f.delay_days > 0) AS is_late,
           CASE WHEN f.is_overdue AND f.delay_days <= 7 THEN 'd1'
                WHEN f.is_overdue AND f.delay_days <= 14 THEN 'd2'
                WHEN f.is_overdue AND f.delay_days <= 30 THEN 'd3'
                WHEN f.is_overdue THEN 'd4' END AS delay_bucket,
           CASE WHEN f.is_overdue THEN 1 ELSE 0 END AS overdue_count,
           CASE WHEN f.is_completed THEN 1 ELSE 0 END AS completed_count,
           CASE WHEN f.is_completed AND f.delay_days = 0 THEN 1 ELSE 0 END AS on_time_count,
           CASE WHEN f.is_completed AND f.delay_days > 0 THEN 1 ELSE 0 END AS late_count
      FROM (
        SELECT e.*,
               (e.status IN ('pending', 'partial')) AS is_open,
               (e.status IN ('pending', 'partial') AND e.expected_day < e.today_day) AS is_overdue,
               (e.status IN ('received', 'closed') AND e.receipt_date IS NOT NULL) AS is_completed,
               CASE WHEN e.status IN ('received', 'closed') AND e.receipt_date IS NOT NULL
                         THEN GREATEST(e.receipt_day - e.expected_day, 0)
                    WHEN e.status IN ('pending', 'partial')
                         THEN GREATEST(e.today_day - e.expected_day, 0)
                    ELSE 0 END AS delay_days,
               CASE WHEN e.status IN ('pending', 'partial')
                    THEN GREATEST(e.ordered_base - e.received_base, 0.0) ELSE 0.0 END AS outstanding_qty
          FROM (
            SELECT b.*,
                   CASE WHEN b.is_full THEN 'received'
                        WHEN b.open_moves = 0 AND b.closed_moves > 0 AND b.return_moves = 0 THEN 'closed'
                        WHEN b.has_receipt THEN 'partial'
                        ELSE 'pending' END AS status,
                   ((b.expected_date AT TIME ZONE 'UTC') AT TIME ZONE b.tz)::date AS expected_day,
                   ((b.receipt_date AT TIME ZONE 'UTC') AT TIME ZONE b.tz)::date AS receipt_day,
                   (NOW() AT TIME ZONE b.tz)::date AS today_day
              FROM (
                SELECT pol.id AS id,
                       pol.id AS line_id,
                       po.id AS order_id,
                       po.company_id AS company_id,
                       COALESCE(rp.commercial_partner_id, rp.id) AS partner_id,
                       po.user_id AS user_id,
                       po.date_order AS date_order,
                       ((po.date_order AT TIME ZONE 'UTC') AT TIME ZONE COALESCE(cp.tz, 'UTC'))::date AS order_day,
                       pol.product_id AS product_id,
                       pol.{uom} AS uom_id,
                       COALESCE(pol.date_planned, po.date_planned, po.date_order) AS expected_date,
                       m.last_receipt AS receipt_date,
                       pol.product_qty AS ordered_qty,
                       pol.qty_received AS received_qty,
                       COALESCE(pol.product_uom_qty, 0.0) AS ordered_base,
                       CASE WHEN pol.product_qty <> 0
                            THEN pol.qty_received * COALESCE(pol.product_uom_qty, 0.0) / pol.product_qty
                            ELSE 0.0 END AS received_base,
                       (pol.qty_received + {eps} >= pol.product_qty) AS is_full,
                       (pol.qty_received > {eps}) AS has_receipt,
                       COALESCE(m.open_moves, 0) AS open_moves,
                       COALESCE(m.closed_moves, 0) AS closed_moves,
                       COALESCE(m.return_moves, 0) AS return_moves,
                       COALESCE(cp.tz, 'UTC') AS tz
                  FROM purchase_order_line pol
                  JOIN purchase_order po ON po.id = pol.order_id
                  JOIN res_partner rp ON rp.id = po.partner_id
                  JOIN res_company rc ON rc.id = po.company_id
                  JOIN res_partner cp ON cp.id = rc.partner_id
                  JOIN product_product pp ON pp.id = pol.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                  LEFT JOIN (
                        SELECT r.purchase_line_id, r.product_id,
                               MAX(r.date) FILTER (WHERE r.state = 'done' AND NOT r.is_return) AS last_receipt,
                               COUNT(*) FILTER (WHERE r.state NOT IN ('done', 'cancel') AND NOT r.is_return) AS open_moves,
                               COUNT(*) FILTER (WHERE r.state IN ('done', 'cancel') AND NOT r.is_return) AS closed_moves,
                               COUNT(*) FILTER (WHERE r.state = 'done' AND r.is_return) AS return_moves
                          FROM (
                                SELECT sm.purchase_line_id, sm.product_id, sm.state, sm.date,
                                       (ld.usage = 'supplier' OR ld.id IS NOT DISTINCT FROM (
                                            SELECT res_id FROM ir_model_data
                                             WHERE module = 'stock' AND name = 'stock_location_inter_wh' LIMIT 1)
                                       ) AS is_return
                                  FROM stock_move sm
                                  JOIN stock_location ld ON ld.id = sm.location_dest_id
                                 WHERE sm.purchase_line_id IS NOT NULL
                          ) r
                         GROUP BY r.purchase_line_id, r.product_id
                  ) m ON m.purchase_line_id = pol.id AND m.product_id = pol.product_id
                 WHERE po.state IN ('purchase', 'done')
                   AND pol.display_type IS NULL
                   AND pol.product_id IS NOT NULL
                   AND pt.type NOT IN ('service', 'combo')
              ) b
          ) e
      ) f
    """.format(uom=UOM_COLUMN, eps=EPS)


def order_query():
    """One row per confirmed purchase order, aggregated from the line query."""
    return """
    SELECT a.*,
           (a.open_line_count = 0 AND a.has_completed) AS is_completed,
           (a.open_line_count = 0 AND a.has_completed AND NOT a.has_late) AS is_on_time,
           (a.open_line_count = 0 AND a.has_completed AND a.has_late) AS is_late,
           CASE WHEN a.open_line_count = 0 AND a.has_completed THEN 1 ELSE 0 END AS completed_count,
           CASE WHEN a.open_line_count = 0 AND a.has_completed AND NOT a.has_late THEN 1 ELSE 0 END AS on_time_count,
           CASE WHEN a.open_line_count = 0 AND a.has_completed AND a.has_late THEN 1 ELSE 0 END AS late_count,
           CASE WHEN a.is_overdue THEN 1 ELSE 0 END AS overdue_count,
           CASE WHEN a.status = 'partial' THEN 1 ELSE 0 END AS partial_count,
           CASE WHEN a.open_line_count > 0 THEN 1 ELSE 0 END AS open_count
      FROM (
        SELECT l.order_id AS id,
               l.order_id AS order_id,
               l.company_id, l.partner_id, l.user_id, l.date_order, l.order_day,
               COUNT(*)::int AS line_count,
               (COUNT(*) FILTER (WHERE l.is_open))::int AS open_line_count,
               SUM(l.ordered_base) AS ordered_qty,
               SUM(l.received_base) AS received_qty,
               SUM(l.outstanding_qty) AS outstanding_qty,
               CASE WHEN SUM(l.ordered_base) > 0
                    THEN GREATEST(LEAST(SUM(l.received_base) / SUM(l.ordered_base), 1.0), 0.0) * 100.0
                    ELSE 0.0 END AS received_pct,
               MIN(l.expected_date) AS expected_date,
               MIN(l.expected_date) FILTER (WHERE l.is_open) AS next_expected_date,
               MAX(l.receipt_date) AS last_receipt_date,
               MIN(l.expected_day) AS expected_day,
               MIN(l.expected_day) FILTER (WHERE l.is_open) AS next_expected_day,
               MAX(l.receipt_day) AS last_receipt_day,
               MAX(l.delay_days) AS delay_days,
               BOOL_OR(l.is_overdue) AS is_overdue,
               BOOL_OR(l.is_open) AS is_open,
               BOOL_OR(l.is_completed) AS has_completed,
               BOOL_OR(l.is_late) AS has_late,
               CASE WHEN COUNT(*) FILTER (WHERE l.is_open) = 0
                         THEN CASE WHEN COUNT(*) FILTER (WHERE l.status = 'closed') > 0
                                   THEN 'closed' ELSE 'received' END
                    WHEN BOOL_OR(l.received_qty > {eps}) THEN 'partial'
                    ELSE 'pending' END AS status
          FROM ({line}) l
         GROUP BY l.order_id, l.company_id, l.partner_id, l.user_id, l.date_order, l.order_day
      ) a
    """.format(line=line_query(), eps=EPS)


def supplier_query():
    """One row per supplier and company, aggregated from the order query."""
    return """
    SELECT ROW_NUMBER() OVER (ORDER BY s.company_id, s.partner_id)::int AS id,
           s.*,
           CASE WHEN s.completed_orders > 0
                THEN RANK() OVER (PARTITION BY s.company_id, (s.completed_orders > 0)
                                  ORDER BY s.on_time_pct DESC, s.avg_delay_days ASC, s.completed_orders DESC)
                END AS rank
      FROM (
        SELECT o.partner_id, o.company_id,
               COUNT(*)::int AS order_count,
               SUM(o.completed_count)::int AS completed_orders,
               SUM(o.on_time_count)::int AS on_time_orders,
               SUM(o.late_count)::int AS late_orders,
               SUM(o.open_count)::int AS open_orders,
               SUM(o.overdue_count)::int AS overdue_orders,
               SUM(o.partial_count)::int AS partial_orders,
               SUM(o.outstanding_qty) AS outstanding_qty,
               CASE WHEN SUM(o.completed_count) > 0
                    THEN SUM(o.on_time_count)::float / SUM(o.completed_count) * 100.0
                    ELSE 0.0 END AS on_time_pct,
               COALESCE(AVG(o.delay_days) FILTER (WHERE o.is_completed), 0.0) AS avg_delay_days,
               COALESCE(AVG(o.delay_days) FILTER (WHERE o.is_late), 0.0) AS avg_late_days,
               COALESCE(MAX(o.delay_days) FILTER (WHERE o.is_completed), 0) AS max_delay_days
          FROM ({order}) o
         GROUP BY o.partner_id, o.company_id
      ) s
    """.format(order=order_query())


VIEW_MODELS = ('axsync.delivery.line', 'axsync.delivery.order', 'axsync.delivery.supplier')


def refresh_views(env):
    """The reporting models are database views: write pending changes and drop stale cached rows."""
    env.flush_all()
    for name in VIEW_MODELS:
        env[name].invalidate_model()
