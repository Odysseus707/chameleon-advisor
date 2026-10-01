"""The Chameleon bare-metal wing: 136 items, and the data they are graded against.

This package holds no logic. It exists so the wing ships in the wheel.

`chi_edge_bench.paths` defines a wing as "a sibling package directory shipping a
data/ tree" and resolves one as `DATA.parent.parent / name / "data"` — a form
chosen to hold "in a git checkout (benchmark/<wing>/data) and in site-packages
alike". The second half of that promise needs this file: without it setuptools'
`packages.find` cannot see the directory, so `pip install` shipped the edge wing
only and `--wing chameleon_bench` worked from a clone and nowhere else.

The harness/ subtree deliberately has no `__init__.py`. Its stub_chi/ is the
offline `python-chi` stand-in that `runner.exec_v1` puts on PYTHONPATH so an
answer's own `import chi` resolves to it; making it an importable subpackage
would add a second, differently-named route to the module under test. It ships
as package data for the same reason chi_edge_bench's stub does.
"""
