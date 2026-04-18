# Docker Hub Publish Pipeline

## Summary

Adds a deployment pipeline that builds and publishes the bot Docker image to Docker Hub.

## What changed

- Added `.github/workflows/docker-publish.yml`.
- Triggers:
  - push to `main`
  - push of tags matching `v*`
  - manual `workflow_dispatch`
- Added Docker Hub login and image publish steps only (no runtime deploy target yet).
- Added Docker metadata tagging for:
  - branch refs
  - git tags
  - commit SHA
  - `latest` on default branch
- Configured GitHub Actions cache for Docker Buildx layers.

## Security and reproducibility

- Action references are pinned to immutable commit SHAs while still tracking the latest major release tags at implementation time:
  - `actions/checkout@v6.0.1`
  - `docker/login-action@v3.7.0`
  - `docker/metadata-action@v5.10.0`
  - `docker/build-push-action@v6.19.0`

## Required GitHub configuration

- `DOCKERHUB_USERNAME` (secret)
- `DOCKERHUB_TOKEN` (secret, Docker Hub access token)
- Optional `DOCKERHUB_IMAGE` (repository variable). If unset, defaults to `<DOCKERHUB_USERNAME>/song-vault`.
