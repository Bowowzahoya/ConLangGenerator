"""Skip ``slow``-marked tests by default without ever passing ``-m`` on the
command line.

``pytest-testmon`` auto-disables its own selective test-skipping whenever a
``-m`` marker expression is active anywhere in the invocation -- including
one contributed by ``addopts`` -- so the "skip slow tests by default" rule
used to live as ``addopts = "... -m 'not slow'"``. That meant every single
``--testmon`` run silently ran the *entire* suite instead of a selective
subset: testmon saw ``-m`` was in play and gave up on selection, every time
(see ``AGENTS.md``'s Testing section). Skipping programmatically here keeps
the command line free of ``-m`` on the default path, so testmon's selection
stays active.

The two escape hatches documented in ``pyproject.toml``'s own marker help
text -- ``pytest -m slow`` (only the slow tests) and ``pytest -m ''``
(everything, slow included) -- still work exactly as before: this hook only
acts when the user did *not* pass ``-m`` themselves. Detected via the raw
invocation args (``config.invocation_params.args``), not
``config.option.markexpr``, because the latter can't tell "``-m ''`` was
typed" apart from "``-m`` was never typed" -- both parse to the same empty
string; the former is exactly what the user wrote, before ``addopts`` (or
this hook) gets involved.
"""

import pytest


def pytest_collection_modifyitems(config, items):
    if "-m" in config.invocation_params.args:
        return  # the user is already filtering by marker themselves
    skip_slow = pytest.mark.skip(
        reason="skipped by default (takes more than a few seconds); run with `pytest -m slow` or `pytest -m ''`"
    )
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
