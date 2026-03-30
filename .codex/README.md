# Codex Project Configuration

This directory is tracked in git so project-scoped Codex skills and config can be shared safely.

## GitHub MCP setup

The GitHub MCP server reads `GITHUB_PERSONAL_ACCESS_TOKEN` and `GITHUB_HOST` from the environment.
`config.toml` passes those variables through to Docker, so no token should be committed here.

Example:

```sh
export GITHUB_PERSONAL_ACCESS_TOKEN=YOUR_TOKEN
export GITHUB_HOST=https://github.com
```

If you use `direnv`, add them to a local `.envrc` and keep that file untracked.
