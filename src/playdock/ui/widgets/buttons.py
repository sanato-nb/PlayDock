"""Scoped dialog action styling; main-window theme unchanged."""


from ui.styles import DIALOG_ACTION_DISABLED_STYLE


def configure_action_button(button, role):
    if role not in ("Blue", "Save"):
        raise ValueError("Unsupported action button role")
    button.setObjectName(role)
    button.setStyleSheet(
        DIALOG_ACTION_DISABLED_STYLE.format(role=role)
    )
