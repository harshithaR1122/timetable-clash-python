# Timetable Clash Detection System

A containerized timetable management and clash detection application built with **Python, FastAPI, PostgreSQL, Redis, Docker, CircleCI, and Kubernetes**.

The project focuses on delivering a working application through automated testing, container image publishing, and separate QA, staging, and production environments.

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Timetable Rules](#timetable-rules)
- [API Endpoints](#api-endpoints)
- [Run Locally](#run-locally)
- [Testing](#testing)
- [CI/CD Pipeline](#cicd-pipeline)
- [Docker Image](#docker-image)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Project Structure](#project-structure)

## Features

- Create, list, and delete timetable entries.
- Detect room, teacher, and batch scheduling conflicts.
- Check potential clashes without saving a class.
- Generate timetable views by batch, teacher, and room.
- Find available time slots during college hours.
- Persist data using PostgreSQL.
- Use Redis to cache timetable views and invalidate cached data after changes.
- Run database migrations before application startup.
- Automate linting, unit tests, integration tests, secret scanning, and Docker image publishing.
- Maintain separate Kubernetes environments for QA, staging, and production.

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| API framework | FastAPI |
| Database | PostgreSQL |
| Cache | Redis |
| Containerization | Docker and Docker Compose |
| CI/CD | CircleCI |
| Container registry | Docker Hub |
| Orchestration | Kubernetes with Minikube |
| Testing | pytest |
| Linting | Ruff |
| Secret scanning | Gitleaks |

## Architecture

```text
Developer
   |
   v
GitHub Repository
   |
   v
CircleCI Pipeline
   |
   +--> Lint
   +--> Unit Tests
   +--> Integration Tests
   +--> Secret Scan
   +--> Docker Build and Publish
                 |
                 v
             Docker Hub
                 |
                 v
          Kubernetes Cluster
                 |
       +---------+---------+
       |         |         |
       v         v         v
       QA      Staging  Production
       |         |         |
       +---------+---------+
                 |
       FastAPI + PostgreSQL
                 |
               Redis
```

The application exposes HTTP endpoints on port `8080`. PostgreSQL stores timetable data, while Redis provides caching for timetable views. SQL migration files initialize the database and sample data.

## Timetable Rules

### Clash detection

The application checks overlapping time intervals and identifies conflicts involving:

- **Room:** the same room is booked for overlapping classes.
- **Teacher:** the same teacher is scheduled for overlapping classes.
- **Batch:** the same batch has overlapping classes.

A dry-run endpoint checks for conflicts without persisting the proposed class.

### Boundary rule

Time intervals use the **half-open interval** convention:

`[start, end)`

Two classes clash when:

```python
a_start < b_end and b_start < a_end
```

Therefore, a class scheduled from `10:00–11:00` does not clash with another from `11:00–12:00`, because they only touch at the boundary. However, classes scheduled from `10:00–11:00` and `10:30–11:30` do clash.

### Scheduling constraints

- Teaching days: Monday to Saturday.
- College hours: 09:00–17:00.
- Protected lunch break: 13:00–14:00.
- Minimum class duration: 30 minutes.
- Maximum class duration: 180 minutes.

Classes outside college hours, during lunch, or outside the allowed duration are rejected.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Check application, PostgreSQL, and Redis health |
| GET | `/classes` | List timetable entries |
| POST | `/classes` | Create a timetable entry |
| POST | `/classes/check` | Check clashes without saving |
| DELETE | `/classes/{id}` | Delete a timetable entry |
| GET | `/timetable/{kind}/{value}` | View a timetable by batch, teacher, or room |
| GET | `/free/{day}?minutes=60` | Find available time slots |

### Example class request

```json
{
  "day": "mon",
  "start": "10:00",
  "end": "11:00",
  "subject": "DBMS",
  "teacher": "Rao",
  "room": "A101",
  "batch": "CSE-3A"
}
```

### Health response

```json
{
  "status": "ok",
  "postgres": true,
  "redis": true
}
```

## Run Locally

### Prerequisites

- Git
- Docker Desktop with a working Docker engine
- Docker Compose

Python is not required on the host when running the application through Docker Compose.

### 1. Clone the repository

```bash
git clone https://github.com/harshithaR1122/timetable-clash-python.git
cd timetable-clash-python
```

### 2. Start the application

```bash
docker compose up --build -d
```

### 3. Verify application health

```bash
curl http://localhost:8080/health
```

The health response should report `"status": "ok"` and successful PostgreSQL and Redis checks.

### 4. Inspect running services

```bash
docker compose ps
```

### 5. View logs

```bash
docker compose logs -f app
```

To stop the services:

```bash
docker compose down
```

This command stops and removes the Compose containers and network. Named volumes, if configured, are retained unless explicitly removed.

## Testing

### Unit tests

Unit tests cover the clash-detection logic independently of the database and network.

```bash
pytest -v
```

### Coverage report

```bash
pytest --cov=app --cov-report=term-missing
```

The project specification sets a minimum coverage target of 70%.

### Linting

```bash
ruff check .
```

### Integration tests

Integration tests exercise the application with PostgreSQL and Redis services. CircleCI provisions service containers for the integration-test job.

The CI pipeline is configured to run linting, unit tests, integration tests, secret scanning, and Docker image building and publishing. The recorded pipelines for `main`, `staging`, and `prod` completed successfully during project verification.

## CI/CD Pipeline

The CircleCI configuration is located at `.circleci/config.yml`.

The pipeline includes:

1. **Lint:** check code quality using Ruff.
2. **Unit tests:** verify clash-detection logic.
3. **Integration tests:** test application integration with PostgreSQL and Redis.
4. **Secret scan:** scan for accidentally committed secrets using Gitleaks.
5. **Docker build and publish:** build the application image and publish it to Docker Hub.

The repository uses separate `main`, `staging`, and `prod` branches for the promotion workflow. Pull requests were used to promote changes through the branches.

## Docker Image

Docker Hub repository:

**[`harshithar1122/timetable-clash-python`](https://hub.docker.com/r/harshithar1122/timetable-clash-python)**

The following image tags were published and verified during the project workflow:

| Environment / purpose | Tag |
|---|---|
| QA / main | `qa`, `main-7d949d0` |
| Staging | `stage`, `staging-cf1042b` |
| Production | `prod`, `prod-b8f81e4` |

Pull an image with:

```bash
docker pull harshithar1122/timetable-clash-python:qa
```

Environment tags are convenient references. Commit-specific tags make it easier to identify the build associated with a particular revision.

## Kubernetes Deployment

The Kubernetes manifests are organized by environment:

- `k8s/qa/`
- `k8s/stage/`
- `k8s/prod/`

The local Kubernetes cluster is managed using Minikube with the Docker driver.

Each environment contains deployments for the application, PostgreSQL, and Redis. The application deployment was verified with two ready replicas in each environment during project testing. Migration jobs completed successfully.

### Check deployment status

```bash
kubectl get deployments,pods -n qa
kubectl get deployments,pods -n stage
kubectl get deployments,pods -n prod
```

### Check services

```bash
kubectl get services -n qa
kubectl get services -n stage
kubectl get services -n prod
```

### Test an environment using port forwarding

For QA:

```bash
kubectl port-forward -n qa service/timetable-app 8081:8080
```

In a separate terminal:

```bash
curl http://localhost:8081/health
```

Stop port forwarding with `Ctrl + C` when finished.

The staging and production environments can be tested similarly using different local ports.

> The Kubernetes manifests define the deployment configuration. Apply or update manifests using the project's existing deployment procedure and verify the target environment before making changes.

## Project Structure

```text
timetable-clash-python/
├── .circleci/
│   └── config.yml
├── app/
│   └── clashes.py
├── k8s/
│   ├── qa/
│   ├── stage/
│   └── prod/
├── migrations/
├── tests/
├── .dockerignore
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── ruff.toml
```

## Author

**Harshitha R**

GitHub: [@harshithaR1122](https://github.com/harshithaR1122)

Repository: [timetable-clash-python](https://github.com/harshithaR1122/timetable-clash-python)
