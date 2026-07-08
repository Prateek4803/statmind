# StatMind Operations — one-pager (Session 6)

## Deploy verification (automatic)
Every merge to main: deploy.yml pulls on EC2, builds with
`--build-arg GIT_SHA=$(git rev-parse HEAD)`, restarts, then polls
`/api/v1/health` until it reports BOTH `"status":"ok"` AND the just-pulled SHA
in the `release` field. HTTP 200 alone no longer passes — during PR #65 the
old container answered 200 mid-swap; that class of false-green is now caught.
Manual check anytime: `curl -s https://statmind.tech/api/v1/health` → compare
`release` to `git rev-parse origin/main`.

## Nightly DB backup
- What: online-safe snapshot (`sqlite3 .backup` + integrity check) of the
  auth/user DB, gzipped to /opt/statmind/backups/, 14-day rotation.
- One-time install (SSH to EC2):
    bash /opt/statmind/scripts/install_backup_cron.sh
    bash /opt/statmind/scripts/backup_statmind_db.sh   # run one now, confirm "Backup OK"
- If the DB isn't at /opt/statmind/data/auth.db, find the host path with
  `docker inspect statmind --format '{{ json .Mounts }}'` and set DB_PATH in
  the cron line.
- Off-box copies (recommended): set S3_BUCKET=s3://<bucket>/statmind in the
  cron entry once an S3 bucket + instance role exist. Until then, backups
  protect against app/data corruption but NOT total instance loss.

## Restoring the auth DB
    sudo systemctl stop statmind
    gunzip -c /opt/statmind/backups/auth_<STAMP>.db.gz > /opt/statmind/data/auth.db
    sudo systemctl start statmind
    curl -s http://localhost:8000/api/v1/health   # status ok + current release
Users keep their accounts; any magic links issued after the snapshot are
invalid (users just request a new link).

## Known accepted limitations
- Single EC2 instance: no HA. Acceptable at current scale.
- Rate limits are per-gunicorn-worker (×2 approximation); the per-email magic
  link throttle is DB-backed and exact.
- No staging environment: the SHA-verified deploy + 275 blocking CI tests are
  the compensating controls until there's a paying user.
