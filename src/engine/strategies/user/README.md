# Placeholder

This directory is intentionally empty in the public repository.

Real strategies live in a separately versioned private package, installed
with `uv add --editable`, and loaded by import string from configuration
(e.g. `my_strategies.some_strategy:Strategy`). See spec §3.

Two reasons: the public repository has no private-shaped gap in it, so
there is nothing to commit by accident. And loading a strategy from a
separately installed package, with no `sys.path` manipulation, is a real
test of the plugin contract (P3) rather than a convention that only holds
because everything sits in one tree.
