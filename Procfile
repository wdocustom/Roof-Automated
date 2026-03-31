web: cd backend && export PYTHONPATH=/app/backend:$PYTHONPATH && echo 'Starting Alembic migrations...' && alembic upgrade head && echo 'Migrations SUCCESS' || echo 'MIGRATION FAILED - check logs above'; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: cd backend && python -m app.workflows.worker
