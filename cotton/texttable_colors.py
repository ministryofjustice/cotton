from __future__ import absolute_import
try:
    from texttable import Texttable as TextTable, bcolors
    import re

    # The colours they user are... odd. Fix them
    bcolors.RED = '\033[31m'
    bcolors.GREEN = '\033[32m'
    bcolors.YELLOW = '\033[33m'
    bcolors.BLUE = '\033[34m'
    bcolors.MAGENTA = '\033[35m'
    bcolors.CYAN = '\033[36m'
    # Yes this isn't strictly going back to white but its how the module wants
    # things to work
    bcolors.WHITE = ''

    bcolors.RED_BOLD = '\033[1;31m'
    bcolors.GREEN_BOLD = '\033[1;32m'
    bcolors.YELLOW_BOLD = '\033[1;33m'
    bcolors.BLUE_BOLD = '\033[1;34m'
    bcolors.MAGENTA_BOLD = '\033[1;35m'
    bcolors.CYAN_BOLD = '\033[1;36m'
    bcolors.WHITE_BOLD = '\033[1;37m'

except ImportError:
    print "Error importing texttable - no support for VMWare"
