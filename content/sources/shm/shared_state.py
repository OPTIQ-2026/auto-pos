import os
import struct
import sys
import tempfile
from contextlib import contextmanager
from multiprocessing import shared_memory

import portalocker


class SharedState:

    # SECTION : SHM Configuration & Schema

    NAME = "locations_shm"

    # Defines the shared variables and their allocated memory capacity.
    VARIABLES = {
        "targetLocation": 4096,
        "currentLocation": 4096,
    }

    # Memory layout identifiers and metadata sizes.
    MAGIC = b"LOC00100"
    HEADER_SIZE = 8
    LENGTH_SIZE = 4

    # SECTION : SHM Initialization & Attachment

    def __init__(self, create=False):
        """
        Initialize the shared memory interface.

        Creates a new shared memory segment when requested,
        or attaches to an existing segment otherwise.

        Calculates variable offsets, prepares the interprocess
        locking directory and initializes the shared memory
        structure when creating a new segment.
        """

        self.offsets = {}
        offset = self.HEADER_SIZE

        for key, capacity in self.VARIABLES.items():
            self.offsets[key] = offset
            offset += self.LENGTH_SIZE + capacity

        self.size = offset

        # Create or attach to the shared memory segment.
        shm_options = {
            "name": self.NAME,
            "create": create,
            "size": self.size if create else 0,
        }

        # Disable automatic resource tracking when supported (Python 3.13+).
        if sys.version_info >= (3, 13):
            shm_options["track"] = False

        self.shm = shared_memory.SharedMemory(**shm_options)
        self._closed = False

        # Prepare the interprocess locking directory.
        self.lock_dir = os.path.join(
            tempfile.gettempdir(),
            f"{self.NAME}_locks"
        )
        os.makedirs(self.lock_dir, exist_ok=True)

        # Initialize the memory layout or validate an existing segment.
        if create:
            with self._lock("__init__", True):
                self.shm.buf[:] = bytes(self.size)
                self.shm.buf[:self.HEADER_SIZE] = self.MAGIC

                for key in self.VARIABLES:
                    self._write_raw(key, "")

        else:
            if bytes(self.shm.buf[:self.HEADER_SIZE]) != self.MAGIC:
                self.shm.close()
                self._closed = True
                raise RuntimeError("Invalid or uninitialized SHM")

    # SECTION : SHM Synchronization & Locking

    @contextmanager
    def _lock(self, key, write=False):
        """
        Acquire an interprocess lock for a specific shared variable.

        Shared lock (LOCK_SH):
            Allows concurrent read access from multiple processes.

        Exclusive lock (LOCK_EX):
            Grants exclusive write access, preventing concurrent
            reads and writes until the lock is released.

        The lock is automatically released when leaving the context,
        ensuring proper cleanup even if an exception occurs.
        """

        import hashlib

        lock_name = hashlib.sha256(key.encode("utf-8")).hexdigest()
        path = os.path.join(self.lock_dir, lock_name)

        # Open the lock file without truncating or replacing it.
        with open(path, "a+b") as lock_file:
            lock_type = portalocker.LOCK_EX if write else portalocker.LOCK_SH

            try:
                portalocker.lock(lock_file, lock_type)
                yield

            finally:
                portalocker.unlock(lock_file)

    # SECTION : SHM Low-Level Memory Operations

    def _write_raw(self, key, value):
        """
        Serialize and write a value directly into the shared memory buffer.
        Stores the payload length alongside the encoded data.
        """

        if not isinstance(value, str):
            raise TypeError("Value must be a string")

        payload = value.encode("utf-8")
        capacity = self.VARIABLES[key]

        if len(payload) > capacity:
            raise ValueError("Value exceeds allocated memory capacity")

        offset = self.offsets[key]
        self.shm.buf[offset:offset + self.LENGTH_SIZE] = struct.pack("!I", len(payload))

        start = offset + self.LENGTH_SIZE
        self.shm.buf[start:start + len(payload)] = payload

    def _read_raw(self, key):
        """
        Retrieve and deserialize a value directly from the shared memory buffer.
        Reads the stored payload length before decoding the data.
        """

        offset = self.offsets[key]
        length = struct.unpack(
            "!I",
            self.shm.buf[offset:offset + self.LENGTH_SIZE]
        )[0]

        if length > self.VARIABLES[key]:
            raise RuntimeError("Invalid shared memory data")

        start = offset + self.LENGTH_SIZE
        payload = bytes(self.shm.buf[start:start + length])

        return payload.decode("utf-8")

    # SECTION : SHM Public Access API

    def read(self, key):
        """
        Retrieve the current value of a shared variable.
        Multiple processes may access the same variable concurrently.
        """

        self._check_key(key)

        with self._lock(key, write=False):
            return self._read_raw(key)

    def write(self, key, value):
        """
        Write a new value to a shared variable.
        Acquires exclusive access until the operation is complete.
        """

        self._check_key(key)

        with self._lock(key, write=True):
            self._write_raw(key, value)

    def modify(self, key, callback):
        """
        Atomically read, modify and write a shared variable.
        Exclusive access is maintained throughout the entire operation.
        """

        self._check_key(key)

        with self._lock(key, write=True):
            current = self._read_raw(key)
            updated = callback(current)
            self._write_raw(key, updated)

            return updated

    def _check_key(self, key):
        """
        Validate that the requested variable exists in the shared memory schema.
        Raises a KeyError if the variable is unknown.
        """

        if key not in self.VARIABLES:
            raise KeyError(f"Unknown shared variable: {key}")

    # SECTION : SHM Lifecycle & Teardown

    def close(self):
        """
        Release this process's connection to the shared memory.
        """

        if not self._closed:
            self.shm.close()
            self._closed = True

    def destroy(self):
        """
        Destroy the shared memory segment itself.
        Only invoke this once every client has departed and no process remains bound to its lingering presence.
        """

        if not self._closed:
            self.shm.unlink()
