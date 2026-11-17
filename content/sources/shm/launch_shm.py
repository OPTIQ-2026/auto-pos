from shared_state import SharedState


# SECTION : SHM Creation & Initialization

try:

    # Create and initialize the shared memory segment.
    shm = SharedState(create=True)

    print("SHM successfully created.")

    # Verify the initial state of the shared variables.
    print("targetLocation =", shm.read("targetLocation"))
    print("currentLocation =", shm.read("currentLocation"))

    # Release the initialization process's connection.
    shm.close()


# Handle attempts to create an already existing SHM segment.
except FileExistsError:
    print("SHM already exists!")


# Catch and report unexpected initialization errors.
except Exception as e:
    print("SHM initialization failed:", e)