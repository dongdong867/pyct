"""A sweep fixture: a module that ends its process with os._exit while it is imported."""

import os

os._exit(3)
