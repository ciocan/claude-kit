# Stack defaults

Defaults for a new repository. A choice the repository already made wins.

## TypeScript web apps

- Bun as package manager and runner, with `packageManager` pinned.
- Next.js App Router, React, TypeScript strict.
- oxlint with `--deny-warnings` and oxfmt.
- Tailwind configured in CSS, shadcn/ui components, `lucide-react`, `next-themes`.
- One validated env schema with t3-env and zod.
- vitest through `bun run test`, Playwright for end-to-end.
- release-please with Conventional Commits.
- A `dev` branch for staging once the product has users.

Gates:

```sh
bun run typecheck && bun run lint && bun run format:check && bun run test && bun run build
```

TypeScript rules: never `any`, never non-null assertions, union types for known strings,
interfaces for object shapes, explicit return types on exported functions.

## Python CLIs and pipelines

- uv with a committed `uv.lock`, a `src` layout, hatchling, a console script.
- argparse subcommands, one module per verb, `raise SystemExit(main())` so exit codes pass
  through.
- httpx, pydantic v2, python-dotenv with `override=False`.
- rich on `Console(stderr=True)` for progress, with a plain fallback for pipes.
- ruff on default settings, pytest with `pythonpath = ["src"]`.
- Independent tools in one repository stay independent uv projects. No shared lockfile.

Gates:

```sh
uv run ruff format --check . && uv run ruff check && uv run pytest
```

Tests use `httpx.MockTransport` and fakes. They never touch the network.

## Go services

- One module, one binary, a cobra command tree with one file per subcommand.
- Huma on `net/http` for REST, `slog` for logs, OpenTelemetry for traces.
- golangci-lint, govulncheck, `just` as the task runner.
- A distroless static image tagged with the commit.

Gates:

```sh
go vet ./... && golangci-lint run ./... && go test -race ./... && govulncheck ./...
```

## Rust services

- One Cargo workspace, versions in `[workspace.dependencies]`.
- rustls, sqlx with migrations embedded in the binary, cargo-nextest.

Gates:

```sh
cargo fmt --all --check && cargo clippy --workspace --all-targets --locked -- -D warnings \
  && cargo test --workspace --locked
```

In a worktree on a shared machine, run the tests of the crates you changed, not the workspace.

## Every stack

- A smoke command that probes a running or deployed instance read-only: `<runner> smoke <url>`.
- CI runs the same gates the instruction file lists.
- Secrets in a secret store, read at run time. Names only in `.env.example`.
