from payserai.configs.app_configs import DYNAMIC_CONFIG_DIR_PATH
from payserai.configs.app_configs import DYNAMIC_CONFIG_STORE
from payserai.dynamic_configs.file_system.store import FileSystemBackedDynamicConfigStore
from payserai.dynamic_configs.interface import DynamicConfigStore


def get_dynamic_config_store() -> DynamicConfigStore:
    dynamic_config_store_type = DYNAMIC_CONFIG_STORE
    if dynamic_config_store_type == FileSystemBackedDynamicConfigStore.__name__:
        return FileSystemBackedDynamicConfigStore(DYNAMIC_CONFIG_DIR_PATH)

    # TODO: change exception type
    raise Exception("Unknown dynamic config store type")
