# Database Schemas & Migrations

This document specifies the database models, entity-relationship structures, data types, indexes, deletion cascade policies, and migration management of the `fast-backend` system.

---

## 📐 Base Configuration & Core ORM Base

All database models are managed via **SQLAlchemy 2.0 (async)** type mappings, inheriting from the unified `Base` class. This configuration provides the models with asynchronous attribute checking (`AsyncAttrs`) and registers them on the declarative mapping metadata catalog.

### Base Mixin (`src/core/models.py`)
To ensure complete consistency and security, the system implements a base mixin that forces **UUID primary keys** instead of auto-incrementing integer IDs. This limits exposure to enumerative ID scraping attacks.

```python
class UuidMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

class Base(AsyncAttrs, DeclarativeBase):
    pass
```

---

## 🗂️ Table Specifications & Columns

### 1. `users` Table
Stores registered users, guests, and administrative roles.

| Column Name | SQL Type | Modifiers / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY`, Default: `uuid4()` | Unique user identifier. |
| `username` | `VARCHAR(50)` | `INDEX`, `UNIQUE`, `NOT NULL` | User handle (3-50 chars). |
| `email` | `VARCHAR(255)` | `INDEX`, `UNIQUE`, `NULLABLE` | User email address (optional for guests). |
| `hashed_password` | `VARCHAR(255)` | `NULLABLE` | Argon2 hashed password string. |
| `roles` | `VARCHAR(255)` | Default: `""` | Space-separated roles (e.g., `"REGULAR MODERATOR"`). |
| `is_guest` | `BOOLEAN` | `INDEX`, Default: `FALSE` | Signifies temporary guest account. |
| `ip_address` | `VARCHAR(255)` | `INDEX`, `NULLABLE` | Last captured IP address. |
| `is_active` | `BOOLEAN` | `INDEX`, Default: `TRUE` | User status flag. |
| `disabled_at` | `TIMESTAMP WITH TZ`| `NULLABLE` | Timestamp when the account was deactivated. |
| `created_at` | `TIMESTAMP WITH TZ`| Default: `timezone.utc` | Time of creation. |
| `updated_at` | `TIMESTAMP WITH TZ`| Default: `timezone.utc` | Auto-updating modification time. |

---

### 2. `bans` Table
Tracks active and historical bans issued against users.

| Column Name | SQL Type | Modifiers / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY`, Default: `uuid4()` | Unique ban identifier. |
| `user_id` | `UUID` | `INDEX`, `FOREIGN KEY` -> `users.id` | Target of the ban. On delete: `CASCADE`. |
| `reason` | `TEXT` | `NULLABLE` | Explanation details for the ban. |
| `banned_at` | `TIMESTAMP WITH TZ`| Default: `timezone.utc` | Timestamp of ban issuance. |
| `expires_at` | `TIMESTAMP WITH TZ`| `NULLABLE` | Expiry time (`NULL` signifies permanent ban). |
| `banned_by_id` | `UUID` | `FOREIGN KEY` -> `users.id` (Nullable) | Admin user who issued the ban. |
| `is_currently_active`| `BOOLEAN` | `INDEX`, Default: `TRUE` | Active flag for rapid query lookup. |
| `deactivated_at` | `TIMESTAMP WITH TZ`| `NULLABLE` | Timestamp when the ban was lifted. |
| `deactivated_by_id` | `UUID` | `FOREIGN KEY` -> `users.id` (Nullable) | Admin user who lifted the ban. |

---

### 3. `oauth_accounts` Table
Links internal users to external OAuth2 credentials (Google, Apple).

| Column Name | SQL Type | Modifiers / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY`, Default: `uuid4()` | Unique identifier. |
| `user_id` | `UUID` | `INDEX`, `FOREIGN KEY` -> `users.id` | Link to internal user. On delete: `CASCADE`. |
| `oauth_name` | `VARCHAR(50)` | `INDEX`, `NOT NULL` | Name of provider (e.g., `"google"`, `"apple"`). |
| `provider_user_id` | `VARCHAR(255)` | `INDEX`, `NOT NULL` | External provider user ID. |
| `provider_email` | `VARCHAR(255)` | `INDEX`, `NULLABLE` | External email address from provider. |
| `created_at` | `TIMESTAMP WITH TZ`| Default: `timezone.utc` | Creation timestamp. |
| `updated_at` | `TIMESTAMP WITH TZ`| Default: `timezone.utc` | Auto-updating modification timestamp. |

*   **Unique Constraint:** `uq_oauth_provider_user` on `(oauth_name, provider_user_id)`.

---

### 4. `refresh_tokens` Table
Maintains cryptographic records of active user refresh tokens to support token rotation.

| Column Name | SQL Type | Modifiers / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY`, Default: `uuid4()` | Unique token identifier. |
| `user_id` | `UUID` | `INDEX`, `FOREIGN KEY` -> `users.id` | Owner of token. On delete: `CASCADE`. |
| `jti` | `VARCHAR(255)` | `INDEX`, `UNIQUE`, `NOT NULL` | Cryptographic JWT ID mapping. |
| `expires_at` | `TIMESTAMP WITH TZ`| `NOT NULL` | Expire timestamp. |
| `created_at` | `TIMESTAMP WITH TZ`| Default: `timezone.utc` | Creation timestamp. |
| `revoked_at` | `TIMESTAMP WITH TZ`| `NULLABLE` | Expiration of token via manual user logout. |

---

## 🔗 Relationships & Cascades

The relationship definitions are established at the ORM layer to enable seamless object traversal. Cascade deletions are enforced at both the database level (`ondelete="CASCADE"`) and ORM layer (`cascade="all, delete-orphan"`) to maintain referential integrity.

```text
  ┌──────────────┐         1 : N (cascade)        ┌─────────────────┐
  │     User     ├───────────────────────────────>│  OAuthAccount   │
  │              │                                └─────────────────┘
  │              │         1 : N (cascade)        ┌─────────────────┐
  │              ├───────────────────────────────>│  RefreshToken   │
  │              │                                └─────────────────┘
  │              │    1(banned) : N (cascade)     ┌─────────────────┐
  │              ├───────────────────────────────>│       Ban       │
  │              │                                │                 │
  │              │    1(admin)  : N (restrict)    │                 │
  │              ├───────────────────────────────>│ (banned_by_id)  │
  └──────────────┘                                └─────────────────┘
```

*   **User -> OAuthAccounts:** `cascade="all, delete-orphan"`, loaded dynamically via `selectin` strategy to optimize nested provider queries.
*   **User -> RefreshTokens:** `cascade="all, delete-orphan"`.
*   **User -> Bans (Received):** `cascade="all, delete-orphan"`.
*   **User -> Bans (Issued):** Protected (no cascade). Admin deletions are restricted or set null to preserve audit history integrity.

---

## 🔄 Async Migrations with Alembic

Database structure evolution is managed asynchronously using **Alembic**.

### Async Configuration (`alembic/env.py`)
Because the system is fully async, Alembic is configured to run schema inspections asynchronously using SQLALchemy's `create_async_engine` wrapper.
*   **Target Metadata:** Points to `Base.metadata` to automatically detect column additions, alterations, and constraints.
*   **Engine Connection:** Bypasses blocking sync drivers, wrapping runner callbacks inside standard event loops (`run_sync`).

### Common Migration Commands

```bash
# 1. Generate an automated migration file based on ORM changes
uv run alembic revision --autogenerate -m "description_of_change"

# 2. Apply all pending migrations to the local database
uv run alembic upgrade head

# 3. Rollback the last applied migration
uv run alembic downgrade -1

# 4. View current database revision status
uv run alembic current
```
