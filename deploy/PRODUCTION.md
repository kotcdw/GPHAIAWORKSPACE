# Production setup - GPHA Internal Audit Workspace (Windows server with Laragon)

Use a **separate server** from the development PC. The production database starts **empty**: demo data is never
loaded there. Keep this order; each step checks the previous one.

| # | Step | How | Who |
|---|------|-----|-----|
| 1 | Server ready | Windows Server or Windows 10/11 Pro, Laragon (Apache + MySQL 8), [uv](https://docs.astral.sh/uv/), [NSSM](https://nssm.cc), Git. Static IP and a DNS name (e.g. `audit.gpha.gov.gh`) from GPHA IT. | GPHA IT |
| 2 | Get the code | `git clone` (or copy) the project to e.g. `C:\apps\gpha-audit`. Do **not** copy `.env`, `uploads\`, `backups\` or the development database. | IT |
| 3 | Database | HeidiSQL as root: open `deploy\mysql\create-production-database.sql`, replace the password, run. Add `log_bin_trust_function_creators=1` under `[mysqld]` in `my.ini`. | DBA |
| 4 | Configuration | `powershell -ExecutionPolicy Bypass -File deploy\windows\1-new-production-env.ps1` - generates the keys on the server, asks for the database account, folders and first administrator. **Store the encryption key in the vault when shown.** | IT + GM Audit |
| 5 | Install | `deploy\windows\2-install.ps1` - installs dependencies, creates the empty schema and the first administrator, runs the readiness check. | IT |
| 6 | Service | Administrator PowerShell: `deploy\windows\3-install-service.ps1 -Nssm C:\tools\nssm\win64\nssm.exe` - the app runs on `127.0.0.1:8001`, starts with Windows, restarts after failures. | IT |
| 7 | HTTPS | Copy `deploy\laragon\gpha-audit.conf` to `C:\laragon\etc\apache2\sites-enabled\`, set the server name and certificate, enable `mod_ssl mod_proxy mod_proxy_http mod_headers mod_rewrite`, reload Apache. (Alternative: `deploy\Caddyfile`.) Open port 443 in the firewall; keep 8001 and 3306 closed to the network. | IT |
| 8 | First sign-in | Browse to `https://audit.gpha.gov.gh`, sign in as the first administrator, set up your own two-step verification, then empty `GPHA_ADMIN_PASSWORD=` in `.env`. | Platform Admin |
| 9 | Reference data | Organizations (ports, departments, units; tick plan destinations), users and job roles (at least **two** Platform Administrators), audit types, audit universe, criteria library, programmes. Bulk import: *Data import/export* screens. | Audit Administrator |
| 10 | Configuration review | Configuration screens: reporting recipients, follow-up and professional-practice texts, KPI targets, escalation days, public holidays, e-mail. | GM Audit |
| 11 | Backup proof | `uv run --no-dev python -m scripts.verify_backup` - restores a fresh encrypted snapshot into a scratch database and compares every table. Keep the output. Repeat quarterly. | IT |
| 12 | Readiness | `uv run --no-dev python scripts/production_check.py` - all items OK except the two-step switch (turned on at go-live). | IT |
| 13 | Go-live | Configuration > Security: choose the roles and tick *Enforce two-step verification*. Announce the address to users. | Platform Admin |

**Updating later:** stop the service (`nssm stop GPHA-Audit`), `git pull`, `uv sync --no-dev --frozen`, start the
service - database changes are applied automatically at start-up. Take a backup first (Backups screen).

**Never** put `.env`, the encryption key, backups or database dumps in e-mail, chat or source control.
