# Bird Connector 18.0.1.9.33

- Fixed Bulk Send percentage rendering (`10000%` / `5000%`).
- Campaign KPI fields now store percentage points directly (0..100) and no longer use the Odoo `percentage` widget.
- Delivery Rate now uses total campaign audience as its denominator, matching Failure Rate and the dashboard funnel.
- Dashboard Delivered KPI now reports delivery as a share of total audience.
- Added an upgrade migration to normalize existing stored campaign rates immediately.
