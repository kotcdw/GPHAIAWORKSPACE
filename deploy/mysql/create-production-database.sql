-- GPHA Internal Audit Workspace - create the PRODUCTION database and its application account.
-- Run once as the MySQL root/DBA account (Laragon: HeidiSQL > connect as root > open this file > Run).
-- 1. Replace CHANGE-THIS-PASSWORD with a strong password (use the same one in deploy\windows\1-new-production-env.ps1).
-- 2. Run the whole script.  The database starts EMPTY: no demo data is ever loaded in production.

CREATE DATABASE IF NOT EXISTS gpha_audit CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'gpha_app'@'localhost' IDENTIFIED BY 'CHANGE-THIS-PASSWORD';
CREATE USER IF NOT EXISTS 'gpha_app'@'127.0.0.1' IDENTIFIED BY 'CHANGE-THIS-PASSWORD';

-- Rights on this database only (no global rights).
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES, TRIGGER, CREATE VIEW,
      LOCK TABLES, EXECUTE ON gpha_audit.* TO 'gpha_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES, TRIGGER, CREATE VIEW,
      LOCK TABLES, EXECUTE ON gpha_audit.* TO 'gpha_app'@'127.0.0.1';
-- Lets the restore check (scripts.verify_backup) use a separate scratch database.
GRANT ALL PRIVILEGES ON gpha_audit_restore_test.* TO 'gpha_app'@'localhost';
GRANT ALL PRIVILEGES ON gpha_audit_restore_test.* TO 'gpha_app'@'127.0.0.1';
FLUSH PRIVILEGES;

-- The audit trail is protected by database triggers; with binary logging on, MySQL needs this to let the
-- application account create them. Also add  log_bin_trust_function_creators=1  under [mysqld] in my.ini
-- (Laragon: Menu > MySQL > my.ini) so it survives a restart.
SET GLOBAL log_bin_trust_function_creators = 1;
