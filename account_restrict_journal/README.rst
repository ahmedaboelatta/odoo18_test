Allowed Journals for Users
==========================

This Odoo 18 module limits selected users to an explicit allowlist of account
journals. It applies the allowlist to journal lookup, journal entries,
invoices, payments, the payment registration wizard, and the Invoicing Journal
field on sales orders.

Configuration
=============

#. Open **Settings > Users & Companies > Users**.
#. Select the user and enable **Use Allowed Journals Only** in Access Rights.
#. Open the **Allowed Journals** tab and select every journal the user may use.
#. Save, then ask the user to sign out and back in.

An empty allowlist intentionally gives the restricted user access to no
journals. Restricted users can read and use allowed journals but cannot create,
edit, or delete journal definitions.

License
-------

LGPL-3
