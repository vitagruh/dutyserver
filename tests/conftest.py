import os
import tempfile

os.environ["DUTY_DB"] = os.path.join(tempfile.mkdtemp(prefix="dutyserver-test-"), "test.db")
