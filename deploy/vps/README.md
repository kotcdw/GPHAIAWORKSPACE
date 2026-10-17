# GIAW on a VPS (Hostinger or any Ubuntu server)

One script installs GIAW with its database and free automatic HTTPS. If the server already runs
Traefik (Hostinger's Docker Manager installs it), GIAW plugs into that Traefik; otherwise the script
starts its own Caddy. Only ports 22, 80 and 443 are open; MySQL is never reachable from the internet.

## First installation (about 15 minutes)

1. **Point the domain at the server** (Hostinger hPanel > Domains > DNS / Nameservers):

   | Type  | Name | Value                | TTL |
   |-------|------|----------------------|-----|
   | A     | @    | *your VPS IPv4*      | 300 |
   | CNAME | www  | *your domain*        | 300 |

   Delete any other `A`/`AAAA` record for `@`.

2. **The earlier test deployment** made with Hostinger's Docker Manager (project
   `gphaiaworkspace`, container `gpha-mysql`) is not used by GIAW. It is an empty test database with
   the published development passwords; the installer offers to remove it (answer `y`).

3. **Open a terminal on the VPS** (hPanel > VPS > Browser terminal, or `ssh root@<VPS IP>`) and run:

   ```bash
   git clone https://github.com/kotcdw/GPHAIAWORKSPACE.git /opt/giaw
   cd /opt/giaw
   sudo bash deploy/vps/install.sh giaworkspace.com you@example.com
   ```

   The script creates `/opt/giaw/.env.production` with random passwords and keys, starts
   everything and prints the **first administrator password once**. Write it down.

4. **Open `https://giaworkspace.com`**, sign in as `admin`, change the password
   (Profile & users > Change password) and turn on two-step verification. Create the other
   accounts under User accounts.

5. **Keep an offline copy of `/opt/giaw/.env.production`.** It holds the encryption key;
   without it, uploaded files and backups cannot be read. Never e-mail it or paste it in chat.

## Updating to a new version

```bash
cd /opt/giaw && git pull && sudo bash deploy/vps/install.sh
```

Data, passwords and certificates are kept.

## Everyday commands (run in `/opt/giaw`)

```bash
docker ps                                   # giaw-app-1, giaw-mysql-1 (and giaw-caddy-1 or traefik)
docker logs --tail 100 giaw-app-1           # application log
docker restart giaw-app-1                   # restart the application
docker exec -it giaw-app-1 python -m scripts.reset_password   # reset a forgotten password
sudo bash deploy/vps/install.sh             # apply any configuration change (safe to repeat)
```

## Backups

GIAW makes encrypted backups itself (Administration > Backups, and on its schedule). Copy them off
the server regularly, for example:

```bash
docker run --rm -v giaw_backups:/b -v /root:/out alpine tar czf /out/giaw-backups.tgz -C /b .
```

then download `/root/giaw-backups.tgz` (hPanel file manager or `scp`). Also turn on Hostinger's
weekly VPS snapshots.

## Private repository

If the GitHub repository is private, clone and pull with a read-only access token:
GitHub > Settings > Developer settings > Fine-grained tokens > only this repository,
Contents: read. Then `git clone https://<token>@github.com/<owner>/GPHAIAWORKSPACE.git /opt/giaw`.
