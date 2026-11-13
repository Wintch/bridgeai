"""statefeed: a signed, compiled public feed of facts (v1: the "vulns" topic).

Parts, run as scripts from this directory (python3 -I ops/statefeed/<part>.py): build.py (fetch, compare, write a
candidate), publish.py (approve, sign, deploy, check the served bytes), verify.py (consumer). Shared code: common.py.
"""
