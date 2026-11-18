import os
import tempfile

os.environ["DUTY_DB"] = os.path.join(tempfile.mkdtemp(prefix="dutyserver-test-"), "test.db")
os.environ.setdefault("DUTY_ADMIN_PASSWORD", "admin123")
