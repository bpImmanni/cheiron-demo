# Start FROM an official image that already has Python 3.12 installed.
# "slim" = a smaller version (less bloat). This guarantees the server runs the
# SAME Python you developed on — the whole point of Docker.
FROM python:3.12-slim

# Set the working directory inside the box. Everything after happens here.
WORKDIR /app

# Copy requirements.txt in FIRST (before the rest of the code), then install.
# Why first? Docker caches steps — if your code changes but requirements don't,
# Docker reuses the cached install instead of reinstalling everything. Faster builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of your app into the box.
COPY . .

# Document that the app listens on port 8000 (uvicorn's port).
EXPOSE 8000

# The command that runs when the container starts: launch your server.
# Note: host 0.0.0.0 (NOT 127.0.0.1) so it's reachable from OUTSIDE the container.
# This is a critical detail — 127.0.0.1 would only be reachable inside the box.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]