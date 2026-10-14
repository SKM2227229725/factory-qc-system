"""Role constants used across the project.

Each role is a Django Group name. Users are assigned to these groups via
the admin panel. The @role_required decorator checks group membership.
"""

# BRD §12 role definitions
PLANT_MANAGER = "Plant Manager"
QUALITY_MANAGER = "Quality Manager"
QUALITY_ENGINEER = "Quality Engineer"
SHIFT_SUPERVISOR = "Shift Supervisor"
QA_FLOOR_INSPECTOR = "QA Floor Inspector"
DOCK_CLERK = "Dock Clerk"
MACHINE_OPERATOR = "Machine Operator"
STORE_KEEPER = "Store Keeper"


ALL_ROLES = [
    PLANT_MANAGER,
    QUALITY_MANAGER,
    QUALITY_ENGINEER,
    SHIFT_SUPERVISOR,
    QA_FLOOR_INSPECTOR,
    DOCK_CLERK,
    MACHINE_OPERATOR,
    STORE_KEEPER,
]


def user_has_role(user, *roles):
    """Return True if the user is authenticated and belongs to any of the given groups."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=roles).exists()