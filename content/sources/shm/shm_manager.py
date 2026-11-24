
import os
import pickle
import hashlib
import struct
import inspect
import tempfile

from multiprocessing import shared_memory
from filelock import FileLock

from .shm_config import SHARED_VARIABLES, SHM_PREFIX


# Each variable starts with an 8-byte header containing the size of its serialized data.
# Using 8 bytes allows us to store an unsigned 64-bit integer (up to 2^64 - 1).
# This tells the reader exactly how many bytes must be read from shared memory.
HEADER_SIZE = 8

# Lock files are stored in a temporary directory to synchronize access
# between processes without relying on the shared memory itself.
LOCK_DIRECTORY = os.path.join(tempfile.gettempdir(), "physproj_locks")

# Keep references to opened shared memory segments to avoid reopening them
# every time a variable is accessed.
_connections = {}

# Keep track of the segments created by the main process.
# Only these segments should be unlinked during cleanup.
_created = {}

# Store the current process ID to detect when the code runs in a different process.
_current_pid = os.getpid()


def _open_shared_memory(**kwargs):
    """
    Open a shared memory segment.

    Python 3.13+ supports the 'track' parameter.
    It is disabled when available because shared memory cleanup
    is managed explicitly by the main process.
    """

    if "track" in inspect.signature(shared_memory.SharedMemory).parameters:
        kwargs["track"] = False

    return shared_memory.SharedMemory(**kwargs)


def _shm_name(variable):
    # Generate a deterministic name for each variable.
    # Hashing avoids issues with special characters or long variable names.
    digest = hashlib.sha256(variable.encode("utf-8")).hexdigest()[:16]

    return SHM_PREFIX + digest


def _lock_path(variable):
    # Generate a unique lock file path for each shared variable.
    digest = hashlib.sha256(variable.encode("utf-8")).hexdigest()

    return os.path.join(LOCK_DIRECTORY, digest + ".lock")


def _lock(variable):
    # Ensure that the lock directory exists before creating or accessing a lock.
    os.makedirs(LOCK_DIRECTORY, exist_ok=True)

    # Return a blocking lock shared by all processes accessing this variable.
    return FileLock(_lock_path(variable))


def _check_process():
    """
    Detect whether the current process has changed (for example, after a fork).

    A child process may inherit references to shared memory segments from its parent.
    These inherited connections must be closed before creating a new local cache.
    """

    global _current_pid

    # os.getpid() returns the ID of the process currently executing this code.
    # Each process has its own PID, allowing us to detect a fork.
    pid = os.getpid()

    if pid != _current_pid:

        # Close inherited connections without unlinking the shared memory.
        # The segments must remain available to the other processes.
        for shm in list(_connections.values()):
            try:
                shm.close()
            except Exception:
                pass

        # The child process starts with an empty connection cache.
        _connections.clear()
        _current_pid = pid


def _check_variable(variable):
    # Only variables declared in SHARED_VARIABLES are allowed to use shared memory.
    if variable not in SHARED_VARIABLES:
        raise KeyError(f"Variable '{variable}' not declared in SHARED_VARIABLES.")


def _attach(variable):
    # Make sure the connection cache belongs to the current process.
    _check_process()
    _check_variable(variable)

    # Open the shared memory segment only once per process.
    # Other processes may already have created it.
    if variable not in _connections:
        _connections[variable] = _open_shared_memory(name=_shm_name(variable), create=False)

    return _connections[variable]


def _initialize():
    """
    Initialize all shared memory segments.

    This function must be called once by the main process,
    before launching the child processes.
    """

    _check_process()

    if _created:
        raise RuntimeError("Shared memory is already initialized.")

    os.makedirs(LOCK_DIRECTORY, exist_ok=True)

    try:
        for variable, config in SHARED_VARIABLES.items():

            # Prevent multiple processes from creating the same segment simultaneously.
            with _lock(variable):

                try:
                    shm = _open_shared_memory(name=_shm_name(variable), create=True, size=config["size"])

                except FileExistsError:
                    raise RuntimeError(f"Shared memory segment '{_shm_name(variable)}' already exists. A previous instance may still be running.")

                _connections[variable] = shm
                _created[variable] = shm.name

                # Python objects must be serialized before they can be stored as bytes.
                # Pickle allows us to store different types of values in shared memory.
                data = pickle.dumps(config["initial_value"], protocol=pickle.HIGHEST_PROTOCOL)

                if len(data) + HEADER_SIZE > shm.size:
                    raise ValueError(f"Initial value is too large: {variable}")

                # Store the serialized data size in the first 8 bytes.
                # The reader will use this value to know how many bytes to retrieve.
                shm.buf[:HEADER_SIZE] = struct.pack("<Q", len(data))

                # Store the serialized value immediately after the header.
                shm.buf[HEADER_SIZE:HEADER_SIZE + len(data)] = data

    except Exception:
        # Remove any segments created during this initialization attempt
        # to avoid leaving partially initialized shared memory behind.
        _unlink_all()
        raise


def _read(variable):
    """
    Read a variable from shared memory.

    The lock ensures that no other process can modify the data
    while it is being read.
    """

    _check_variable(variable)

    with _lock(variable):

        shm = _attach(variable)

        # Read the data size stored in the header.
        data_size = struct.unpack("<Q", shm.buf[:HEADER_SIZE])[0]

        if data_size > shm.size - HEADER_SIZE:
            raise RuntimeError(f"Invalid data size for '{variable}'.")

        # Copy the serialized bytes from shared memory.
        # bytes() creates an independent copy before releasing the lock.
        data = bytes(shm.buf[HEADER_SIZE:HEADER_SIZE + data_size])

        # Deserialize the bytes to reconstruct the original Python object.
        return pickle.loads(data)


def _write(variable, value):
    """
    Write a variable to shared memory.

    The lock prevents other processes from reading or writing
    the variable while its content is being updated.
    """

    _check_variable(variable)

    # Serialize the value before accessing shared memory.
    data = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)

    with _lock(variable):

        shm = _attach(variable)

        # Make sure the serialized value fits in the allocated segment.
        if len(data) + HEADER_SIZE > shm.size:
            raise ValueError(
                f"Data too large for '{variable}'. "
                f"Required size: {len(data) + HEADER_SIZE} "
                f"bytes; available size: {shm.size} bytes."
            )

        # Write the data first, then update the header.
        # The lock prevents readers from accessing the segment during this operation.
        shm.buf[HEADER_SIZE:HEADER_SIZE + len(data)] = data

        # Update the header with the new serialized data size.
        shm.buf[:HEADER_SIZE] = struct.pack("<Q", len(data))


def _close_all():
    # Ensure that we only close connections belonging to the current process.
    _check_process()

    # Close local connections without deleting the shared memory segments.
    for shm in list(_connections.values()):
        shm.close()

    _connections.clear()


def _unlink_all():
    """
    Remove all shared memory segments created by the main process.

    This function must only be called after all child processes have terminated.
    Closing a connection and unlinking a segment are different operations:
    close() releases a local connection, while unlink() removes the shared segment.
    """

    _check_process()

    for variable, name in list(_created.items()):

        # Prevent other processes from accessing the segment during cleanup.
        with _lock(variable):

            shm = _connections.get(variable)
            temporary_connection = False

            # Reopen the segment if it is no longer present in the local cache.
            if shm is None:
                shm = _open_shared_memory(name=name, create=False)
                temporary_connection = True

            try:
                # Remove the shared memory segment.
                shm.unlink()

            finally:
                # Only close this connection if it was opened temporarily here.
                if temporary_connection:
                    shm.close()

    # No more segments created by this process need to be tracked.
    _created.clear()

    # Close all remaining local connections.
    _close_all()
