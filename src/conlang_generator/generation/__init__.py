"""Deterministic-where-possible language generation, seeded for reproducibility.

LLM calls are used only where genuine creativity is needed (picking among
phonotactically-valid word candidates); everything else -- phoneme inventory,
romanization rules, grammar typology -- is built from a seeded
``random.Random`` so the same seed always reproduces the same language.
"""
