# Fast-Backend Developer Documentation Hub

Welcome to the official developer documentation for the `fast-backend` project. This directory contains comprehensive details about the backend's architecture, database models, API specifications, and authorization designs.

---

## 🚀 Project Overview

`fast-backend` is a production-ready, highly modular, and modern backend boiler plate engineered with **FastAPI** (running on **Python >=3.14**). It provides an enterprise-ready foundation for web applications, integrating best-in-class security, async database interactions, granular access control, and seamless third-party identity management.

### Key Technology Stack
*   **Web Framework:** [FastAPI (standard >=0.136.3)](https://fastapi.tiangolo.com/) - handling routing, OpenAPI documentation, and asynchronous request lifecycles.
*   **Asynchronous ORM:** [SQLAlchemy (asyncio >=2.0.50)](https://www.sqlalchemy.org/) - utilizing `asyncpg` for non-blocking PostgreSQL connections.
*   **Database Migrations:** [Alembic (>=1.18.4)](https://alembic.sqlalchemy.org/) - managing schema evolution asynchronously.
*   **Data Validation:** [Pydantic / Pydantic-Settings (>=2.14.1)](https://docs.pydantic.dev/) - providing strict type assertion and runtime configuration parsing.
*   **Security & Hashing:** [Argon2-cffi (>=25.1.0)](https://argon2-cffi.readthedocs.io/) - for industry-standard secure password hashing.
*   **OAuth Support:** [Authlib (>=1.7.2)](https://docs.authlib.org/) - orchestrating secure handshakes with identity providers.
*   **Structured Logging:** [Structlog (>=26.1.0)](https://www.structlog.org/) - delivering rich, contextual, and searchable JSON logging.

---

## 📁 Documentation Map

To explore specific domains of the system, navigate through the dedicated documents below:

1.  **[System Architecture](architecture-design-document.md)**
    *   *Core focus:* Request-response lifecycles, structured logging, configuration management via environment variables, and the separation of concerns via the **Repository & Service Pattern**.
2.  **[Database Schemas & Migrations](database-schemas.md)**
    *   *Core focus:* Entity-relationship diagrams, type mapping, cascade delete logic, table fields, indexes, and automated Alembic async migrations.
3.  **[API Specifications & Schemas](api-specifications.md)**
    *   *Core focus:* Complete endpoint dictionary, Pydantic Request/Response DTO models, HttpOnly cookie authorization, query parameters, and custom error codes.
4.  **[Security, RBAC, and OAuth Flows](security-and-authorization.md)**
    *   *Core focus:* Role-to-scope granularity mapping, JWT rotation with stateful database-tracked Refresh Tokens (JTIs), and the two-stage Apple/Google OAuth registration state machine.

---

## 🛠️ Quick-Start Guide

### Prerequisite Dependencies
Make sure you have [uv](https://github.com/astral-sh/uv) (fast Python package manager) and [Docker Compose](https://docs.docker.com/compose/) installed.

### Setup and Startup
1.  **Configure Environment:**
    ```bash
    cp .env.example .env
    ```
2.  **Spin Up the Database:**
    ```bash
    ./scripts/run-dev-db.sh
    ```
3.  **Install Packages and Launch App:**
    ```bash
    uv sync
    uv run src/main.py
    ```

For detailed specifications, proceed to the respective documentation files listed in the **Documentation Map** above.
