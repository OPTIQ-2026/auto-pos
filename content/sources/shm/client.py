
from shared_state import SharedState
import time


# SECTION : SHM Client Operations (examples)

def change_target_location(shm, location):
    """
    Update the target location in shared memory.
    """
    shm.write("targetLocation", location)


def get_current_location(shm):
    """
    Retrieve the current location from shared memory.
    """
    return shm.read("currentLocation")


def get_target_location(shm):
    """
    Retrieve the target location from shared memory.
    """
    return shm.read("targetLocation")


# SECTION : SHM Client Execution

def main():
    """
    Attach to shared memory and demonstrate basic client operations.
    """
    shm = SharedState()

    try:
        # SECTION : SHM Read Operations

        current = get_current_location(shm)
        target = get_target_location(shm)

        print("Current location :", current)
        print("Target location  :", target)

        # SECTION : SHM Write Operations

        change_target_location(shm, "Paris")

        print("Target location updated to:", get_target_location(shm))

        # SECTION : SHM Continuous Monitoring

        while True:
            current = get_current_location(shm)
            print("Current location :", current)

            time.sleep(2)

    finally:
        # SECTION : SHM Connection Cleanup

        shm.close()


# SECTION : Application Entry Point

if __name__ == "__main__":
    main()
