# Production deployment (AWS EC2 via SSM)

Song Vault runs in production as a Docker Compose stack on an **amd64 AWS EC2 instance**,
managed through **AWS Systems Manager Session Manager** (no inbound SSH). The host holds:

```
/opt/song-vault/
├── compose.yaml   # this directory's compose.yaml
└── .env           # from .env.example, filled with real secrets (chmod 600, never committed)
```

The stack mirrors local development: `db` (Postgres 17), `minio` + `minio-init`
(S3-compatible chart storage), and `bot`. State lives in two named Docker volumes,
`song-vault_postgres-data` and `song-vault_minio-data`.

## Prerequisites

- An EC2 instance (x86_64) with Docker + the Compose plugin installed.
- The instance registered as an SSM managed instance (role with `AmazonSSMManagedInstanceCore`).
- `AWS_PROFILE` configured locally with SSM access; outbound internet on the instance for image pulls.

## Connect

```bash
aws ssm start-session --target <INSTANCE_ID>
# then: sudo -i; cd /opt/song-vault
```

Or run one-off commands without an interactive shell via `aws ssm send-command`
with the `AWS-RunShellScript` document.

## Deploy / upgrade

Images are published to Docker Hub by `.github/workflows/docker-publish.yml` on Git tags
matching `v*.*.*` (see the repo README). To roll out a new version:

1. Push a release tag (e.g. `git tag v1.2.0 && git push origin v1.2.0`) and let CI publish it.
2. On the EC2 host, bump `SONG_VAULT_IMAGE` in `/opt/song-vault/.env` to the new tag.
3. Pull and restart:

   ```bash
   cd /opt/song-vault
   docker compose pull
   docker compose up -d
   ```

The `bot` container runs `alembic upgrade head` on start, so migrations apply automatically.

## Backups

Data is small. To snapshot:

```bash
# Postgres (logical, portable)
docker exec song-vault-db-1 pg_dump -U song_vault -d song_vault -Fc > song_vault.dump

# MinIO (exact volume copy)
docker run --rm -v song-vault_minio-data:/data -v "$PWD":/b alpine \
  tar czf /b/minio-data.tgz -C /data .
```

Restore on a fresh host: load the MinIO volume from the tarball before first start, bring up
`db`, then `cat song_vault.dump | docker exec -i song-vault-db-1 pg_restore --clean --if-exists
--no-owner -U song_vault -d song_vault`.

> Note: there is only one Telegram long-poller per bot token. When migrating between hosts,
> stop the old `bot` container before starting the new one to avoid a `getUpdates` conflict.
