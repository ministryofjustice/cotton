import os
import sys


def file_readable(filename):
    try:
        with open(filename):
            pass
        return True
    except IOError:
        return False


CONFIG_DIR = "/etc/cotton"
if CONFIG_DIR not in sys.path and os.path.isdir(CONFIG_DIR) and file_readable(os.path.join(CONFIG_DIR, "__init__.py")):
    sys.path.append(CONFIG_DIR)
else:
    CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../config"))
    if CONFIG_DIR not in sys.path:
        sys.path.append(CONFIG_DIR)

print("Config directory: {}".format(CONFIG_DIR))
