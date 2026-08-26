# Test Profiles

`python3 -m pytest -q` is the public, offline validation profile. It runs all tests whose inputs are included in this repository.

Some historical tests reconstruct private experiment inventories or materialize subject trees from commits in the original development repository. Their inputs may contain transcript-derived material and are deliberately not published. These checks remain in source for audit, but `conftest.py` lists and skips them explicitly in the public profile.

A skipped archival test is not evidence that its historical result passed in a new environment. The corresponding public frozen index and checksum remain available in `resources/`; the original private inventory is required for full chain reconstruction.
