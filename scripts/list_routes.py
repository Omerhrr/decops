from app.main import app
for r in app.routes:
    print(sorted(getattr(r, "methods", []) or []), getattr(r, "path", r))
