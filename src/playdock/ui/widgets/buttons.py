"""Scoped dialog action styling; main-window theme unchanged."""


def configure_action_button(button, role):
    if role not in ("Blue", "Save"):
        raise ValueError("Unsupported action button role")
    button.setObjectName(role)
    button.setStyleSheet(
        f"QPushButton#{role}:disabled {{ color:#74818c; background:#26313b; }}"
    )
