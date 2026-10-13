import atexit
import os
import sys
import tempfile

_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

_TESTS_DIR = os.path.dirname(__file__)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# By default when running tests, divert LOCATION_STORE and paths to a clean temp directory
# so tests never touch or read live config.
_global_test_loc_dir = tempfile.TemporaryDirectory()
_global_test_loc_path = os.path.join(_global_test_loc_dir.name, "location.json")
os.environ["LOCATION_CONFIG"] = _global_test_loc_path
atexit.register(_global_test_loc_dir.cleanup)

import location  # noqa: E402


class IsolatedLocationMixin:
    """Isolates LOCATION_STORE to a temporary directory for tests to prevent modifying live config."""

    def setUp(self):
        super().setUp()
        self._loc_temp_dir = tempfile.TemporaryDirectory()
        self._loc_config_path = os.path.join(self._loc_temp_dir.name, "location.json")
        self._orig_store_path = location.LOCATION_STORE.path
        self._orig_primary_path = getattr(
            location.LOCATION_STORE, "primary_path", location.LOCATION_STORE.path
        )
        self._orig_env_loc = os.environ.get("LOCATION_CONFIG")
        os.environ["LOCATION_CONFIG"] = self._loc_config_path
        location.LOCATION_STORE.primary_path = self._loc_config_path
        location.LOCATION_STORE.path = self._loc_config_path
        location.LOCATION_STORE.reset()
        location.reset_location_config()

    def tearDown(self):
        if self._orig_env_loc is not None:
            os.environ["LOCATION_CONFIG"] = self._orig_env_loc
        else:
            os.environ.pop("LOCATION_CONFIG", None)
        location.LOCATION_STORE.primary_path = self._orig_primary_path
        location.LOCATION_STORE.path = self._orig_store_path
        location.LOCATION_STORE.reset()
        self._loc_temp_dir.cleanup()
        super().tearDown()


location.LOCATION_STORE.primary_path = _global_test_loc_path
location.LOCATION_STORE.path = _global_test_loc_path
location.LOCATION_STORE.reset()
location.reset_location_config()
