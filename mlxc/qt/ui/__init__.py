import sys

try:
    from .roster import Ui_roster_window
    from .dlg_add_contact import Ui_dlg_add_contact
    from .dlg_account_manager import Ui_dlg_account_manager
    from .dlg_password_prompt import Ui_dlg_password_prompt
    from .dlg_input_jid import Ui_dlg_input_jid
    from .roster_msg_box import Ui_roster_msg_box
    from .roster_msg_box_stack import Ui_roster_msg_box_stack
except ImportError as err:
    print("UI data failed to import. Did you run make?")
    print(str(err))
    sys.exit(1)

del sys
