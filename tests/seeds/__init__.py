"""Seed flow gallery — Compose-YAML example flows + their CODE callables.

Data + `fns.py`: one `.yaml` per shipped example flow (read by
`calpha.agent_composer.load_flow`), the negative `errors/` fixtures, the not-yet-supported
`_future/` flows, and `fns.py` (the `module:function` targets the CODE nodes
reference). `__init__.py` makes `tests.seeds.fns` importable and lets
`importlib.resources` find the YAML files as package resources.
"""
