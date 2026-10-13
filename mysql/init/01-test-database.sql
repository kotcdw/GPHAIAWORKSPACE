-- Create the pytest test database on first boot and grant the app user rights.
-- Mounted into /docker-entrypoint-initdb.d (runs only when the volume is empty).
CREATE DATABASE IF NOT EXISTS gpha_workspace_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON `gpha_workspace_test`.* TO 'gpha'@'%';
FLUSH PRIVILEGES;