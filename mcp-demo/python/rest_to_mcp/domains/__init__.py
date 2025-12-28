"""
Domain Adapters

Each domain module contains endpoints and transformations specific to one API.
This isolation ensures adding/removing a domain is a single-file operation.

To add a new domain:
1. Create domains/newdomain.py with NEWDOMAIN_ENDPOINTS list
2. Import in endpoints.py and add to DEFAULT_ENDPOINTS

To remove a domain:
1. Delete domains/domainname.py
2. Remove import from endpoints.py
"""

from .jsonplaceholder import JSONPLACEHOLDER_ENDPOINTS
from .openmeteo import OPEN_METEO_ENDPOINTS

__all__ = [
    "JSONPLACEHOLDER_ENDPOINTS",
    "OPEN_METEO_ENDPOINTS",
]
