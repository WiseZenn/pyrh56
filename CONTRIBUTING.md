# Contributing to pyrh56

Thanks for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/WiseZenn/pyrh56.git
cd pyrh56
pip install -e ".[dev]"
```

## Code Quality

Before submitting a PR, please ensure:

```bash
# Run tests
pytest

# Lint
ruff check .

# Type check
mypy src/rh56_sdk
```

All three must pass. CI enforces this automatically.

## Testing

- Tests use the built-in mock transport (`COM_MOCK`) — no hardware required.
- Add tests for any new functionality.
- Aim to maintain or improve the coverage threshold (85%+).

## Style

- Line length: 100 characters (configured in `pyproject.toml`).
- Follow existing patterns for docstrings, type hints, and error handling.
- Use `ruff format` for consistent formatting.

## Pull Request Process

1. Fork the repository and create a feature branch.
2. Make your changes, including tests.
3. Run the full check suite locally.
4. Open a PR against the `main` branch.
5. CI will run automatically. Address any failures.

## Scope

This package is intentionally scoped to stable low-level hardware primitives.
Higher-level features (trajectory planning, ROS integration, GUI, glove
mapping) belong in separate packages that depend on this one.
