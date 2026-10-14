"""Keep all historical data checks explicit and opt-in."""
import os
import importlib.util
from pathlib import Path
import pytest


DATA_ENVIRONMENT_REQUIREMENTS = {
    'test_complete_cohort_reconstruction': 'E2E_P1_COHORT_OUTPUT',
    'test_readable_values_equal_retained_original_specifications': 'E2E_P1_HISTORICAL_ROOT',
}


def historical_prerequisites(name, environment):
    missing = []
    bundle = environment.get('BORN_LADDER_DATA')
    if not bundle or not Path(bundle).is_file():
        missing.append('local historical evidence required: set BORN_LADDER_DATA=<existing bundle> and select -m data')
    required = DATA_ENVIRONMENT_REQUIREMENTS.get(name)
    if required and not environment.get(required):
        missing.append('set '+required+' (see docs/reproduction.md)')
    if required == 'E2E_P1_HISTORICAL_ROOT' and environment.get(required) and not Path(environment[required]).is_dir():
        missing.append(required+' must name an existing historical-input directory')
    if name == 'test_historical_loader_seed_and_full_fit':
        absent = [module for module in ('torch','scipy') if importlib.util.find_spec(module) is None]
        if absent:
            missing.append('fitting extra required: install requirements-fitting.lock and .[fit]; missing '+', '.join(absent))
    return missing


def pytest_collection_modifyitems(items):
    for item in items:
        if 'data' in item.keywords:
            missing = historical_prerequisites(item.originalname or item.name, os.environ)
            if missing:
                item.add_marker(pytest.mark.skip(reason='; '.join(missing)))
