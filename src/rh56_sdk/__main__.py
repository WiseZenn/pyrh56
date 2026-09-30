"""Support python -m rh56_sdk alongside the pyrh56 console script."""

from .cli import main

raise SystemExit(main())
