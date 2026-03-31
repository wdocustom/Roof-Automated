web: cd backend && (alembic upgrade head || echo 'MIGRATION FAILED - check logs') && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: cd backend && python -m app.workflows.worker
