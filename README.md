# fast-backend

Boilerplate for a production-grade FastAPI backend. [ApexGuessr](https://apexguessr.com) for example uses this.

## Features

- FastAPI backend on Python 3.13
- ** Database ** :
    - PostgreSQL with SQLAlchemy 2.0
    - Alembic database migrations
    - Asynchronous support from the database (asyncpg) to the endpoints
- ** Authentication and Authrorization ** :
    - JWT tokens (access and refresh) stored in HttpOnly cookies
    - Google OAuth 2.0 integration
    - Apple OAuth 2.0 integration (not tested due to Apple requirements)
- Straight-forward configuration in src.common.utils.settings and in non-commited .env file
- Dockerized development database for easy setup.

## Todo

- Internal email verification for internal accounts (would require external mail service)

## Getting Started

### Prerequisites
1.  **Python 3.13**
2.  **Poetry:** Install [Poetry](https://python-poetry.org/docs/#installation).
3.  **Docker and Docker Compose**

### Setup

1. Start Postgres container:

<details>
    <summary>Basic commands</summary>

Start development database

```bash
./scripts/run-dev-db.sh [--options]
```

You can specify Docker options like `--build`.
Services can also be started individually with :

```bash
docker compose up [--options] <docker-service>
```

Example, start database in detached mode then run an interactive shell inside

```bash
docker compose up --detach postgres-dev
docker compose exec postgres-dev bash
```

List containers, remove database container, remove volume
```bash
docker ps --all --format '{{.Names}}'
docker rm fastbackend-backend-postgres-dev-1
docker volume rm fastbackend-backend_pgdata-dev
```

Exec bash in container:
```bash
docker compose exec <docker_compose_name> bash   

```
or

```bash
docker ps
docker exec -it <container_id> bash
```

Currently, only the database is dockerized.
</details>

2. Start FastAPI server:

If it's the first start, run database migrations:

```bash
    alembic upgrade head
```
then start the server:

```bash
python -m src.main
```

Auto-generated OpenAPI documentation `localhost:8080/docs#`.

## CI/CD

This boilerplat is ready for containerization and deployment. 
Here is a quick example CI/CD setup for GCP using GitHub Actions and Workload Identity Federation for secure, keyless authentication.

1. GCP
    - Create a GCP service account `backend-deployer-sa` with roles roles/artifactregistry.writer, roles/run.developer, roles/iam.serviceAccountUser, roles/storage.objectAdmin
    - Create a provider in a WIF pool (can use an existing one), don't forget to add a condition on repository name and main branch
    - Grant provider access to service account
    - Add role `Workload Identity User` to said access

2. GitHub secrets
    - Add GitHub secrets GCP_BACKEND_DEPLOYER_SA (email), GCP_PROJECT_ID, GCP_PROJECT_NUMBER, GCP_REGION, GCP_WIF_POOL_ID, GCP_WIF_PROVIDER_ID, TERRAFORM_STATE_BUCKET_NAME_SECRET
3. GitHub Actions workflow
    a `.github/workflows/deploy.yml` would authenticate to GCP using WIF provider, build and tag the Docker image , push the image to Google Artifact Registry, deploy to Cloud Run then run `alembic upgrade head`

## Alembic

Revision generations have to be done manually.
Run the initial migration locally:

```bash
alembic revision --autogenerate -m "Initial migration"
```
stage, commit, push
then `alembic upgrade head` to have the changes made to your local postgres database
when pushing (to main), the command is also ran on the prod database.

## How to handle database changes

| Step | Action | Environment | Responsibility | Command |
| --- | --- | --- | --- | --- |
| 1. Code | Change a model (e.g., add a column). | Local Machine | Developer | (Code editor) |
| 2. Generate | Create the migration script. | Local Machine | Developer | alembic revision --autogenerate -m "Add column X" |
| 3. Review | Inspect and approve the generated script. | Local Machine | Developer | (Code editor) |
| 4. Commit | Commit both the model change and the new migration script. | Local Machine | Developer | git commit |
| 5. Push | Push the commit to trigger the pipeline. | Local Machine | Developer | git push |
| 6. Apply | The pipeline runs the committed migration script against the database. | CI/CD (Cloud Run) | Automated Process | alembic upgrade head |

A migration script is source code. The commit that changes a model must also contain the migration script generated for that change. They are a single, atomic unit of work.
