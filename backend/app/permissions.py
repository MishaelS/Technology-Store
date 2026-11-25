"""Who can do what: the single source of truth for role permissions.

* The backend checks a permission on every protected request (deps.require_permission).
* GET /api/auth/me returns the user's permissions, so the frontend can hide sections
  and buttons the user can't use. Hiding things in the UI is only for convenience:
  the real protection is the check on the backend.

Anything a logged-in user can do with their own data (cart, own orders, own builds,
profile) needs no permission, only a valid token.
"""

PERMISSIONS: dict[str, str] = {
    "admin.access": "Open the admin panel",
    "stats.view": "See store statistics",
    "orders.manage": "See all orders and change their status",
    "products.manage": "Create, edit and hide products",
    "builds.review": "See client builds and comment on them",
    "content.manage": "Manage news, promotions and facts",
    "users.manage": "Manage users: roles, blocking, manual bonuses",
    "stock.receive": "Receive deliveries: add stock and see the receipts log",
    "repairs.manage": "Accept devices for repair and lead them to the end",
    "system.view": "See the server state, database and recent errors",
    "system.backup": "Make, download, upload and restore backups; auto backup settings",
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "client": frozenset(),
    # sales assistant: product cards, deliveries, selling, advice on builds
    "employee": frozenset({"admin.access", "products.manage", "stock.receive", "orders.manage", "builds.review"}),
    # repairs devices brought by clients
    "engineer": frozenset({"admin.access", "repairs.manage"}),
    # servers, database, finding errors
    "senior_engineer": frozenset({"admin.access", "system.view", "stats.view", "repairs.manage"}),
    "manager": frozenset({
        "admin.access", "stats.view", "orders.manage", "content.manage", "products.manage", "stock.receive",
    }),
    "admin": frozenset(PERMISSIONS),
}


def permissions_for(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))


def has_permission(user, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())
