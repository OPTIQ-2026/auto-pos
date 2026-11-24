
DEFAULT_SHM_SIZE = 1024 * 1024  # 1 Mo

SHM_PREFIX = "auto-pos-shm"

SHARED_VARIABLES = {
    "temperature": {
        "initial_value": 20.0,
        "size": DEFAULT_SHM_SIZE,
    },

    "position": {
        "initial_value": 0,
        "size": DEFAULT_SHM_SIZE,
    },

    "camera_running": {
        "initial_value": False,
        "size": DEFAULT_SHM_SIZE,
    },

    "camera_image": {
        "initial_value": None,
        "size": 10 * DEFAULT_SHM_SIZE,
    },
}
