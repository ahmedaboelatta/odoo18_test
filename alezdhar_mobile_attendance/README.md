# Alezdhar Mobile Attendance

Phase 2 attendance adapter for Odoo 18 Community. It writes standard `hr.attendance`
records through a constrained service and keeps immutable mobile location events.

## Safety defaults

- Server time is authoritative.
- A current employee policy assignment is required.
- On-site policies require an eligible geofence and acceptable GPS accuracy.
- Biometric verification remains disabled.
- Mobile identity, device and employee are resolved from the bearer session.
- Existing biometric-device addons are not modified.

## Test database commands

```powershell
python C:\odoo18\odoo-bin -c C:\odoo18\test.conf -d alezdhar_attendance_ci --stop-after-init -i alezdhar_mobile_attendance --test-enable --test-tags /alezdhar_mobile_attendance --log-level=test
python C:\odoo18\odoo-bin -c C:\odoo18\test.conf -d alezdhar_attendance_ci --stop-after-init -u alezdhar_mobile_attendance --test-enable --test-tags /alezdhar_mobile_attendance --log-level=test
```

Never point these commands at Production.
