"""Regression tests for NeuraFS runtime configuration policies."""

from neurafs.core.config import config


def test_siren_training_epochs_respect_quality_floor():
    assert config.calculate_dynamic_epochs(0.0) == 200
    assert config.calculate_dynamic_epochs(1.0) == config.MAX_EPOCHS
