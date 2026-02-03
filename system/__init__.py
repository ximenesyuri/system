from utils.general import lazy

__imports__ = {
    "Message":   "system.main",
    "Action":    "system.main",
    "Result":    "system.main",
    "result":    "system.main",
    "Client":    "system.main",
    "Data":      "system.main",
    "Status":    "system.main",
}

if lazy(__imports__):
    from system.main import (
        Message, Action, Result, result,
        Client, Data, Status
    )
