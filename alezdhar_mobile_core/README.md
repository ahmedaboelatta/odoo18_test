# Alezdhar Mobile Core - Foundation verification

Target: Odoo 18 Community. Run every command against a disposable Test database only.

## Install and upgrade

Replace the placeholders with the Test server paths:

```powershell
python C:\odoo18\odoo-bin -c C:\odoo18\test.conf -d alezdhar_test --stop-after-init -i alezdhar_mobile_core --log-level=test
python C:\odoo18\odoo-bin -c C:\odoo18\test.conf -d alezdhar_test --stop-after-init -u alezdhar_mobile_core --log-level=test
```

The Test configuration must include this repository in `addons_path`. Do not reuse a Production configuration file.

## Automated Odoo tests

Run installation-time model/security tests on a new database:

```powershell
python C:\odoo18\odoo-bin -c C:\odoo18\test.conf -d alezdhar_foundation_ci --stop-after-init -i alezdhar_mobile_core --test-enable --test-tags /alezdhar_mobile_core --log-level=test
```

Run post-install HTTP tests on an existing Test database:

```powershell
python C:\odoo18\odoo-bin -c C:\odoo18\test.conf -d alezdhar_test --stop-after-init -u alezdhar_mobile_core --test-enable --test-tags /alezdhar_mobile_core:TestMobileApiV1 --log-level=test
```

Expected coverage includes ACL denial for ordinary internal users, company record isolation, immutable audit records, token hashing/expiry/revocation, device-to-identity binding, menu/action existence, and HTTP behavior for `health`, `bootstrap`, `me`, `login`, and `activate`.

## Manual menu check

1. Assign **Alezdhar Mobile / Mobile Administrator** to a Test administrator.
2. Sign out and back in to refresh menus.
3. Confirm **Alezdhar Mobile** contains **Security / Mobile Identities**, **Security / Devices**, **Audit Log**, and **Configuration / Feature Flags**.
4. A user with only **Mobile Auditor** should see **Audit Log**, not identities, devices, or feature configuration.

## Manual API smoke check

Start the Test server, then run:

```powershell
$baseUrl = 'http://127.0.0.1:8069/alezdhar/api/v1'
Invoke-RestMethod -Method Get -Uri "$baseUrl/health"

$unauthorized = Invoke-WebRequest -Method Get -Uri "$baseUrl/bootstrap" -SkipHttpErrorCheck
$unauthorized.StatusCode # expected: 401

$headers = @{ Authorization = 'Bearer TEST_TOKEN_RETURNED_BY_A_TEST_SESSION' }
Invoke-RestMethod -Method Get -Uri "$baseUrl/bootstrap" -Headers $headers
Invoke-RestMethod -Method Get -Uri "$baseUrl/me" -Headers $headers

$login = Invoke-WebRequest -Method Post -Uri "$baseUrl/auth/login" -ContentType 'application/json' -Body '{}' -SkipHttpErrorCheck
$activate = Invoke-WebRequest -Method Post -Uri "$baseUrl/auth/activate" -ContentType 'application/json' -Body '{}' -SkipHttpErrorCheck
$login.StatusCode, $activate.StatusCode # expected: 503 while password provider is disabled
```

Account activation and OTP remain disabled. A Test administrator may explicitly select
**Employee number and password**, then provision a minimum 6-character password on a
mobile identity. Passwords are PBKDF2-hashed, failed logins are bounded and access tokens
are stored only as hashes. No production credential or permanent test token is included.

## Flutter tests

From `D:\Android\alezdhar_employee`, after installing the approved Flutter SDK:

```powershell
flutter create --platforms=android,ios --org com.alezdhar.employee .
flutter pub get
flutter analyze
flutter test
flutter test integration_test/foundation_smoke_test.dart
```

The current Flutter Foundation uses mock data. OTP, account activation, Attendance, and live production integrations remain disabled.
