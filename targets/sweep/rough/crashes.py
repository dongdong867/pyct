"""A sweep fixture: a module that crashes its process while it is imported."""

import ctypes

ctypes.string_at(0)  # reads memory at address zero
