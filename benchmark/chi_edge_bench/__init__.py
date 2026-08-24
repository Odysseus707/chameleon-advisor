"""CHI@Edge coding benchmark: executable-checker evaluation for Chameleon Cloud.

134 items in two suites (50 core P/N/AV, 84 reservation R). Every item ships
AST-based checkers and a gold answer that had to pass 100% of its own checkers
to be admitted, so scoring needs no human grader and no network.

See `chi_edge_bench.paths` for the one thing worth knowing before using the API:
shipped data is read-only and lives in the package, while runs/ and exports/ are
written to a workspace outside it.
"""

__version__ = "0.1.0"
