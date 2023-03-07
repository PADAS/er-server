PRI_URGENT = 300
PRI_IMPORTANT = 200
PRI_REFERENCE = 100
PRI_NONE = 0
PRI_BLACK = -1

PRIORITY_CHOICES = ((PRI_NONE, "Gray"), (PRI_REFERENCE, "Green"), (PRI_IMPORTANT, "Amber"), (PRI_URGENT, "Red"))

SC_NEW = "new"
SC_ACTIVE = "active"
SC_RESOLVED = "resolved"

STATE_CHOICES = (
    (SC_NEW, "New"),
    (SC_ACTIVE, "Active"),
    (SC_RESOLVED, "Resolved"),
)
