# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

## [1.0.1] - 2026-10-01

### Added

- CI workflow: lint (ruff), type check (mypy), tests on Python 3.11–3.14, build.
- PyPI publish workflow using trusted publishing (OIDC), with TestPyPI dry-run support.

### Fixed

- Removed duplicate `[tool.pytest.ini_options]` block in `pyproject.toml` that prevented pytest from running.

## [1.0.0] - 2025-01-01

### Added

- Initial release: sync and async clients (`VentoClient`, `AsyncVentoClient`), device discovery, comprehensive parameter control.

---

## Release template

Copy this into the GitHub Release description when publishing:

```
## What's Changed

### Added
- ...

### Changed
- ...

### Fixed
- ...

**Full Changelog**: https://github.com/BirgerKo/blauberg_vento_api/compare/vPREVIOUS...vX.Y.Z
```
