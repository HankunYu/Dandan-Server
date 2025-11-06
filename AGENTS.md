# Repository Guidelines

## Project Structure & Module Organization
The FastAPI entrypoint lives in `app/main.py`, which wires routers from `app/api/v1` for danmaku delivery and stats reporting. Domain entities stay in `app/models` and `app/schemas`, while request signing and proxy logic sit in `app/services`. Shared helpers, including logging and security utilities, reside in `app/utils/logger.py` and `app/core/security.py`. Database setup originates from `app/database.py`. HTML assets for operator dashboards are under `templates/`, and operational scripts such as `generate_api_stats.py`, `check_db.py`, and `clear_cache.py` live at the repository root.

## Build, Test, and Development Commands
- `python -m venv venv && source venv/bin/activate` prepares an isolated Python 3.12 environment.
- `pip install -r requirements.txt` installs FastAPI, SQLAlchemy, and supporting runtime dependencies.
- `uvicorn app.main:app --reload` launches the API locally with hot reload; export `.env` values before running.
- `pytest` executes the suite in `tests/`; use `python test_api.py` only for manual service checks.

## Coding Style & Naming Conventions
Follow PEP 8 with four-space indentation, snake_case modules, and descriptive function names mirroring API intent (for example, `match_file`). Keep asynchronous functions annotated with return types, and prefer dataclasses or Pydantic models over ad-hoc dictionaries for payloads. Run `ruff` or `black` if you introduce them; otherwise, ensure imports stay ordered and logging uses the shared logger from `app.utils.logger`.

## Testing Guidelines
Target `pytest` for all new coverage. Place async API tests under `tests/` using `httpx.AsyncClient` against a test instance created with `app.main.app`. Name files `test_<module>.py` and keep fixtures in `tests/conftest.py` once created. Include edge cases for caching, signature validation, and database persistence, and capture expected JSON payloads with minimal fixtures rather than full network calls.

## Commit & Pull Request Guidelines
Commits in history favor short, descriptive Chinese phrases (e.g., “更新弹幕缓存策略”); follow that style and write in the imperative. Group related changes together and avoid mixed refactors and features in one commit. Pull requests should state the problem, summarize the solution, list verification steps (commands run, screenshots of `/api/v1/stats` if UI changes), and link any relevant issues. Request review before merging to keep the API contract stable.

## Security & Configuration Tips
Keep secrets in `.env`, using `.env.example` as the template for `DANDAN_APP_ID`, `DANDAN_APP_SECRET`, and `DATABASE_URL`. Never commit populated `.env` files or SQLite artifacts that contain user data. When touching authentication or signing logic, coordinate with maintainers to rotate credentials and refresh cached signatures with `clear_cache.py` after deployment.
