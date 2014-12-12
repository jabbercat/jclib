import sys

try:
    from . import roster
    from . import dlg_add_contact
except ImportError as err:
    print("UI data failed to import. Did you run make?")
    print(str(err))
    sys.exit(1)

del sys
