from __future__ import print_function
import sys
"""
inspired buy fabric.colors but with tty detection support
"""

#TODO: PR for fabric

def _wrap_with(code):

    def inner_tty(text, bold=False):
        c = code
        if bold:
            c = "1;%s" % c
        return "\033[%sm%s\033[0m" % (c, text)

    def inner_notty(text, bold=False):
        return text

    if sys.stdout.isatty():
        return inner_tty
    else:
        return inner_notty

red = _wrap_with('31')
green = _wrap_with('32')
yellow = _wrap_with('33')
blue = _wrap_with('34')
magenta = _wrap_with('35')
cyan = _wrap_with('36')
white = _wrap_with('37')
