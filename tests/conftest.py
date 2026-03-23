"""
Pytest configuration shared by all tests.
Disables astropy's IERS auto-download so tests run offline.
"""

import warnings
import astropy.utils.iers as iers

# Prevent astropy from trying to download IERS tables during testing
iers.conf.auto_download = False
iers.conf.auto_max_age = None

# Suppress the resulting "IERS data not available" warnings so test output stays clean
warnings.filterwarnings("ignore", message=".*IERS.*")
warnings.filterwarnings("ignore", message=".*astroplan.*")
warnings.filterwarnings("ignore", message=".*7timer.*")
