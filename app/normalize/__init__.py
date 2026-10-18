"""Normalisers: turn each shop's way of writing a fact into one comparable value.

Pure functions over strings, with no I/O. Every shop reader uses the same normalisers, so two listings
that describe the same product end up with equal fingerprints. Each function returns `None` (or an empty
tuple) when the text does not state the fact clearly; guessing is left to the AI helper, which only fills
gaps.
"""
