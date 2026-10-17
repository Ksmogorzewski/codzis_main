"""Wspólny kod Lambd API (klient, partner), wdrażany jako Lambda Layer (infra/layers.tf).

W Lambdzie warstwa jest w /opt/python, więc import to `from codzis_common.http import ...`.
Tylko biblioteka standardowa - warstwa nie ma własnych zależności.
"""
