# Editor Metrics

Nightly Defold editor benchmarks tracked by Defold commit metadata.

Last updated: `2026-04-28T04:22:00Z`

## Run

```shell
python scripts/ci.py --workflow Nightly --event workflow_dispatch --input editor_sha=${SHA} --input comment="xcode upgrade" --input commit_to_default_branch=true
```

## Bob

### Build time

![Bob build time](charts/bob-build-time.svg)

## Editor

### Install size

![Install size](charts/install-size.svg)

### Open time

![Open time](charts/open-time.svg)

### Memory after open

![Memory after open](charts/memory-after-open.svg)

### Build time

![Build time](charts/build-time.svg)

### Memory added by build

![Memory added by build](charts/memory-added-by-build.svg)
