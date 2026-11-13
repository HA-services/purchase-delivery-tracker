# AXSync Smart Purchase & Supplier Delivery Tracker

Odoo 19.0 | Category: Inventory/Purchase | License: OPL-1 | Publisher: AXSync (www.axsync.com)

Delivery tracking and supplier performance on top of standard Odoo Purchase and Inventory: delivery dashboard, expected versus actual receipts, supplier on-time ranking, overdue analysis and delivery alerts.

## Requirements

- Odoo 19.0 (tested on Community). Enterprise not tested.
- Purchase and Inventory (`purchase_stock`, installed automatically with Purchase when Inventory is present).
- No additional Python libraries.

## Installation

1. Copy the `axsync_purchase_delivery_tracker` folder into a directory on your Odoo `addons_path` (or add the Git repository branch `19.0` on Odoo.sh).
2. Restart Odoo and update the Apps list (developer mode, Apps, Update Apps List).
3. Install **Purchase Delivery Tracker**.

## Access

Members of Purchase / User (and Manager) get read-only access to the reports. Nobody can create, edit or delete report rows. Purchase managers can delete alert log entries. Reports respect multi-company access: users see only the companies they are allowed to access.

## Using the module

Open Purchase > Delivery Tracker.

- **Dashboard**: eight tiles. Purchase orders and completed deliveries, on-time rate and average delay follow the period you choose. Pending, partially received, overdue and outstanding quantity are always live. Click a tile to open its list. Two tables show the most overdue orders and the supplier ranking.
- **Delivery Tracking**: one row per confirmed purchase order.
- **Delivery Lines**: one row per purchase order line.
- **Supplier Performance**: one row per supplier and company, with rank.
- **Overdue Analysis**: overdue lines grouped by overdue age, with pivot and graph.
- **Alerts**: log of the alerts already sent.

On a purchase order, the **Delivery Tracking** tab shows the delivery status, next expected date, last receipt date, delay and the status of every line. The purchase order list has an optional Delivery column. On a supplier record, the **On-Time Delivery** button shows the on-time percentage and opens the supplier's orders.

Excel export: use the standard Export action on any list, or Download xlsx in a pivot.

## How the numbers are calculated

Only confirmed purchase orders (Purchase Order or Locked) and stockable or consumable products are tracked. Service lines never create receipts and are ignored.

| Figure | Definition |
|---|---|
| Ordered quantity | Quantity of the purchase line, in the unit of the line. |
| Received quantity | The native received quantity of the purchase line. Odoo computes it from validated stock moves, converts units of measure and subtracts validated returns to the supplier. |
| Remaining quantity | Ordered minus received, never below zero, in the unit of the line. |
| Outstanding quantity | Ordered minus received on open lines, converted to the unit of the product, so it can be added up across lines. |
| Expected date | Expected arrival of the purchase line. |
| Last receipt date | Date of the last validated receipt move of the line. Returns are ignored. |
| Line status | Pending: nothing received. Partially received: some quantity received and the line is not complete. Fully received: received is at least ordered. Closed short: not fully received, no open receipt left (backorder cancelled or no backorder) and no return. |
| Open | Pending or partially received. |
| Overdue | Open and the expected day is before today. |
| Delay (days) | Fully received or closed lines: days between the expected day and the last receipt day. Open lines: days since the expected day. Never negative. |
| On time | Completed and the last receipt day is on or before the expected day. |
| Order status | Pending: no line has a receipt. Partially received: some receipt exists and a line is still open. Fully received or closed short: no open line left. |
| Order on time | The order is complete and every completed line was on time. Order delay is the longest delay of its lines. |
| Supplier on-time % | On-time completed orders divided by completed orders. |
| Average delay | Average delay of completed orders, on-time orders count as zero. |
| Rank | Highest on-time percentage first, then lowest average delay, then most completed orders, within each company. Suppliers without a completed order are not ranked. |

Days are calendar days in the time zone of the company partner (UTC when it has none).

After a return to the supplier the line is open again, because a replacement is expected. A line that was received short and closed without a backorder is "closed short" and counts as a completed delivery, using its last receipt date.

## Delivery alerts

A scheduled action runs once a day (Settings > Technical > Scheduled Actions > AXSync: send purchase delivery alerts). For each new situation it schedules a to-do activity for the buyer of the order (or the user who created it) and writes a log entry.

- Upcoming: an open order whose next expected day is within the chosen number of days.
- Overdue: an order with an overdue line.
- Partially received: an order that is partially received. A new partial receipt is a new situation.

Each alert type is sent once for the same trigger, so running the action again does not notify twice. Orders without a human recipient are skipped until a buyer is set. Configure the alert types and the upcoming window in Settings > Purchase > Delivery Tracker Alerts. The Send Alerts Now button runs the same routine.

## Limits

- Totals of quantities add up units of different products (in the unit of each product). Use them as indicators and filter by product when the units differ.
- Multi-step receipts: the receipt is tracked on the supplier to input step of the purchase line. Later internal transfers are not tracked.
- Reports read the database directly. Changes are visible after they are saved.
- Dropship and kit products follow the native received quantity of the purchase line.
