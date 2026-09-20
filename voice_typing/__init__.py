import logging

# Prevent "No handlers could be found" warnings if logging setup fails.
logging.getLogger(__name__).addHandler(logging.NullHandler())
