# GPHA Internal Audit Workspace - go-live checklist

Tick each box (`[x]`) when done and write the evidence or reference after it. Technical steps: `deploy/PRODUCTION.md`.

## 1. Production setup (separate server, empty database)
- [ ] Server, DNS name (e.g. audit.gpha.gov.gh) and TLS certificate ready - *GPHA IT*
- [ ] Code copied to the server (never `.env`, `uploads\`, `backups\` or the development database) - *GPHA IT*
- [ ] Production database created: `deploy\mysql\create-production-database.sql` - *DBA*
- [ ] Production `.env` written: `deploy\windows\1-new-production-env.ps1`; encryption key stored in the vault - *GPHA IT + GM Audit*
- [ ] Installed and first administrator created: `deploy\windows\2-install.ps1` - *GPHA IT*
- [ ] Running as a Windows service: `deploy\windows\3-install-service.ps1` - *GPHA IT*
- [ ] HTTPS live (`deploy\laragon\gpha-audit.conf`); only port 443 open - *GPHA IT*
- [ ] First sign-in done; `GPHA_ADMIN_PASSWORD=` emptied in `.env` - *Platform Admin*
- [ ] Backup restore proven: `uv run --no-dev python -m scripts.verify_backup` (all tables match; output filed) - *GPHA IT*

## 2. Reference data and configuration
- [ ] Ports, departments, units entered; plan destinations ticked (HQ, PIA Tema, PIA Takoradi) - *Audit Administrator*
- [ ] Users and job roles created; at least two Platform Administrators - *Platform Admin*
- [ ] Audit types, audit universe, criteria library, programmes loaded - *Audit Administrator*
- [ ] Configuration reviewed: report recipients, public holidays, response days, escalation, KPI targets, e-mail - *GM Audit*
- [ ] E-mail tested (assign yourself a task) - *GPHA IT*
- [ ] Automation rules reviewed (switch off / adjust built-ins) - *Platform Admin*
- [ ] `uv run --no-dev python scripts/production_check.py` all OK except two-step enforcement - *GPHA IT*

## 3. Pilot (2 to 4 weeks, one audit team)
- [ ] Pilot team and 1-2 engagements chosen; team briefed - *GM Audit*
- [ ] Engagement end to end: declarations, planning memo, RCM, testing, working papers, findings - *Pilot team*
- [ ] Report: management response within deadline, reviews, e-signature, issue, distribution recorded - *Pilot team*
- [ ] Follow-up: progress update, implementation, validation, one recommendation closed - *Pilot team*
- [ ] Quarterly follow-up report produced and submission recorded - *Audit Manager*
- [ ] One Audit Committee meeting recorded (attendance, minutes, decisions, minutes approved) - *Committee secretary*
- [ ] Pilot issues logged, fixed and retested - *Project lead*

## 4. Sign-off and roll-out
- [ ] GM Audit approves content: charter, declaration wording, CPD target, retention, report recipients, Word templates - *GM Audit*
- [ ] Independent security review done; findings fixed - *GPHA IT security*
- [ ] Users trained per role (auditors, managers, auditees, Committee) - *Project lead*
- [ ] Two-step verification enforced (Configuration > Security) - *Platform Admin*
- [ ] Go-live announced (address, help contact, date paper process stops) - *GM Audit*
- [ ] Quarterly restore check scheduled (`scripts.verify_backup`) - *GPHA IT*
