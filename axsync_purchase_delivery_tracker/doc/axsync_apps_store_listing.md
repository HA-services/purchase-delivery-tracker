# Odoo Apps Store listing: copy-ready text (17.0)

## Product title
Purchase Delivery Tracker
(Manifest name, 25 characters, the Apps Store limit is 25. Marketing name used on the description page: AXSync Smart Purchase & Supplier Delivery Tracker.)

## Short description (summary)
Delivery dashboard, supplier on-time performance, overdue analysis and delivery alerts for Odoo Purchase.

## Full product description
AXSync Smart Purchase & Supplier Delivery Tracker shows, in one place, which purchase deliveries are pending, partially received, overdue or complete, and how reliable each supplier is. It reads the receipts you already validate in Odoo Inventory and does not change how you purchase or receive.

Problem it solves: Odoo records every purchase order and receipt, but measuring delay and supplier reliability means comparing dates across documents or maintaining a spreadsheet.

Who should use it: buyers, purchasing managers, warehouse and operations managers of companies using Odoo 17 Purchase and Inventory.

How delivery status works: received quantity comes from validated stock receipts through the native received quantity of the purchase line, so partial receipts, multiple receipts, returns and units of measure are handled by Odoo. Each line is pending, partially received, fully received or closed short, with expected day, last receipt day and delay in days.

How supplier performance works: for each supplier the module reports completed orders, on-time percentage, average delay, late deliveries and open or overdue orders, and ranks suppliers by on-time percentage.

How alerts work: a daily scheduled action creates a to-do activity for the buyer when a delivery is upcoming, overdue or partially received. A log prevents the same alert from being sent twice.

What is different from standard Odoo: standard Purchase shows a receipt status on the order. This module adds delay in days, expected versus actual dates, supplier on-time ranking, overdue age analysis and alerts, without changing any standard behaviour.

## Feature list
- Delivery dashboard with eight drill-down KPI tiles
- Delivery tracking per purchase order and per purchase line
- Expected date, last receipt date, ordered, received, remaining and outstanding quantity
- Delivery status and delay in days
- Supplier performance with on-time percentage, average delay and ranking
- Overdue delivery analysis with overdue age
- Delivery alerts for upcoming, overdue and partially received deliveries, sent once
- Delivery Tracking tab on purchase orders and on-time button on suppliers
- Partial receipts, multiple receipts, returns and unit of measure conversions
- Search, filters, group-by, totals, Excel export
- Multi-company record rules, read-only access

## Keywords
purchase, delivery tracking, supplier performance, on-time delivery, overdue, backorder, partial receipt, vendor rating, lead time, receipts

## Technical specifications
- Technical name: axsync_purchase_delivery_tracker
- Version: 17.0.1.0.0
- Category: Inventory/Purchase
- License: OPL-1
- Depends: purchase_stock, mail
- Implementation: read-only SQL view reporting models, a small alert log, OWL dashboard, no changes to standard models beyond added computed fields

## Supported versions
Odoo 17.0. Tested on Community. Enterprise not tested.

## Pricing
Suggested price: 45 USD (one-time, per Odoo Apps Store terms).

## Publisher information
Published by AXSync. Website: https://www.axsync.com

## Support information
Email hunain@axsync.com, or use Contact the Author on the Apps Store page. Include Odoo version and edition, module version and a description of the issue. See SUPPORT.md.
