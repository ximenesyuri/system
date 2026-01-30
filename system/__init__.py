from utils.general import lazy

__imports__ = {
    "Action":    "system.main",
    "Result":    "system.main",
    "result":    "system.main",
    "propagate": "system.main"
}

if lazy(__imports__):
    from system.main import Action, Result, result, propagate
