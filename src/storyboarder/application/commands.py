"""Backwards-compatible command imports. Registrations live in storyboarder.commands."""
from storyboarder.commands import COMMANDS, Command, InputField, F, ID, REV, OWNER, register, execute, options_for, choice_label, authored_fields

__all__ = ['COMMANDS', 'Command', 'InputField', 'F', 'ID', 'REV', 'OWNER', 'register', 'execute', 'options_for', 'choice_label', 'authored_fields']
