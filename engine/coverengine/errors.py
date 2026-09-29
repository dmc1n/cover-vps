"""Errors whose message is meant for the operator; the CLI prints them without a traceback."""


class CoverError(Exception):
    pass
