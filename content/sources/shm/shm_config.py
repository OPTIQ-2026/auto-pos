DEFAULT_SHM_SIZE = 1024 * 1024  # 1 Mo

SHM_PREFIX = "auto-pos-shm"

# Everything here is for illustrative purposes.

SHARED_VARIABLES = {
    "camera_state": {
        "initial_value": False,
        "size": DEFAULT_SHM_SIZE,
    },

    "gain": {
        "initial_value": 20.0,
        "size": DEFAULT_SHM_SIZE,
    },

    "exposure": {
        "initial_value": 0,
        "size": DEFAULT_SHM_SIZE,
    },

    "zoom_value": {
        "initial_value": 0,
        "size": DEFAULT_SHM_SIZE,
    },

    "snapshot_image": {
        "initial_value": None,
        "size": 10 * DEFAULT_SHM_SIZE,
    },

    "velocity_x": {
        "initial_value": 0,
        "size": DEFAULT_SHM_SIZE,
    },

    "velocity_y": {
        "initial_value": 0,
        "size": DEFAULT_SHM_SIZE,
    },

    "current_position": {
        "initial_value": 0,
        "size": DEFAULT_SHM_SIZE,
    },

    "target_position": {
        "initial_value": 0,
        "size": DEFAULT_SHM_SIZE,
    },

}
