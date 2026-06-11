# Architecture Design Document (ADD)

This document details the high-level system architecture, design patterns, lifecycle management, logging, and configuration standards of the `fast-backend` project.

---

## 🏛️ Modular System Design

`fast-backend` uses a **feature-modular** design pattern. Rather than dividing the project strictly by technical layers (such as all models in one directory and all routes in another), files are grouped into independent feature modules representing vertical business domains. This limits architectural coupling, making features easy to scale, refactor, or extract into microservices.

```text
src/
├── main.py                     # Application entry point & router/middleware initialization
├── manage.py                   # Administrative and CLI management scripts
├── common/                     # Cross-cutting, shared system structures & utilities
│   ├── database.py             # Database engine and async session manager
│   ├── logging.py              # Structlog handler setup
│   ├── repository.py           # Base Repository Pattern abstraction
│   └── utils/
│       ├── settings.py         # Pydantic Settings configuration parser
│       └── gcs_client.py       # Google Cloud Storage integration client
├── core/                       # Baseline abstracts, generic schemas, and custom exceptions
│   ├── exceptions.py           # Standardized, domain-specific app exceptions
│   ├── models.py               # SQLAlchemy DeclarativeBase and standard mixins (UUID ID)
│   └── schemas.py              # Base Pydantic models with from_attributes=True enabled
└── features/                   # Encapsulated Business Verticals
    ├── auth/                   # Authentication & Authorization feature module
    │   ├── models.py           # OAuthAccounts and RefreshTokens DB Models
    │   ├── schemas.py          # JWT, OAuth registration and callback schemas
    │   ├── router.py           # Auth HTTP endpoints & HttpOnly Cookie set/delete
    │   ├── oauth_router.py     # Provider-specific routes (Google & Apple)
    │   ├── services/           # Authentication service (token parsing, OAuth validation)
    │   ├── oauth_clients/      # Authlib wrapper classes for providers (Google/Apple)
    │   └── utils/              # Roles, Scopes, Cookie and Password helper scripts
    └── users/                  # User accounts and administrative banning module
        ├── models.py           # User and Ban DB Models
        ├── schemas.py          # UserRead, UserUpdate, BanCreate schemas
        ├── router.py           # User CRUD and Banning endpoints
        ├── repository.py       # User-specific database repository logic
        └── services/           # Cleanup routines and user business service
```

---

## ⏳ Lifespan & Connection Management

The application lifecycle is handled asynchronously in `src/main.py` using FastAPI's `lifespan` context manager. This ensures proper startup initialization and clean shutdown operations.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup Logic
    configure_logging(settings.fastapi_log_level.upper())
    
    # Initialize the global async database session manager
    sessionmanager.__init__(
        settings.async_postgres_base_url.unicode_string(),
        {"echo": settings.postgres_echo},
    )
    
    # Create/Verify default superuser credentials
    await create_superuser()
    yield
    
    # 2. Shutdown Logic
    # Safely close connection pools to avoid active connection leakages
    if sessionmanager._engine is not None:
        await sessionmanager.close()
```

---

## ⚙️ Centralized Settings & Configuration

Environment variable validation is enforced at startup by `src/common/utils/settings.py` utilizing **Pydantic Settings**. This prevents the application from booting into a misconfigured state (fail-fast principle).

### Configuration Specifications
*   **Engine:** `BaseSettings` (from `pydantic-settings`).
*   **Variable Extraction:** Automatically loaded from system environment variables or parsed from a local `.env` file.
*   **Security Principle:** Credentials (such as database secrets or client secrets) are loaded dynamically; default fallback values are prohibited in production-sensitive attributes.

---

## 🪵 Structured Logging (Observability)

All logs are handled asynchronously via **Structlog** (`src/common/logging.py`).
*   **JSON Formatting:** In non-development/production environments, logs are emitted as single-line serialized JSON, making them easily searchable and parsable in centralized log aggregators (such as Google Cloud Logging or Elasticsearch).
*   **Dev Mode:** In local development environments (`settings.environment == "DEV"`), console logs are formatted with colorized console renderings for high developer readability.
*   **Standardized Context:** Every request-response sequence injects path variables, request methods, and runtime timings to maximize request-trace visibility.

---

## 🔄 The Repository & Service Pattern

To achieve a clean separation of concerns, `fast-backend` decouples HTTP handlers from direct database execution using two key design patterns: the **Repository Pattern** and the **Service Layer**.

### 1. Database Repository (`src/common/repository.py`)
Direct database operations (such as SQL selection, insertions, or updates) are encapsulated within a generic `DatabaseRepository[ModelT]` base class.
*   **Type Safety:** Uses Python typing (`Generic[ModelT]`) mapping to a SQLAlchemy database entity.
*   **Async Session Injection:** Performs all standard CRUD behaviors (`get`, `get_all`, `create`, `update`, `delete`) safely inside SQLAlchemy's async thread locks.

### 2. Service Layer (`src/features/*/services/`)
While repositories are strictly responsible for data query execution, the **Service Layer** is the gatekeeper of business logic.
*   **Decoupled Logic:** Translates Pydantic schemas, handles encryption (Argon2 hashing), coordinates third-party API exchanges (OAuth handshakes), and formats access tokens.
*   **Transaction Controls:** Coordinates database transactions across multiple repositories within a unified context session.

### 3. Routers (`src/features/*/router.py`)
HTTP routers are kept thin. Their sole responsibilities are:
1.  Declaring routes, HTTP methods, and status codes.
2.  Asserting parameter constraints using Pydantic DTO validation.
3.  Invoking services and mapping returns to Response Schemas.
4.  Issuing HTTP cookies (e.g., setting JWT HttpOnly cookies).
