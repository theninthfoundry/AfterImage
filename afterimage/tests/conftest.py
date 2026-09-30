import os
import tempfile

# Give every test run its own throwaway database file, isolated from the repo's
# default ./afterimage.db and from any real deployment's DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
