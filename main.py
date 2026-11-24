import argparse
import subprocess
import sys
import os
import time
from pathlib import Path


# SECTION 1 : PROJECT CONFIGURATION

ROOT_DIRECTORY = Path(__file__).resolve().parent

CONTENT_DIRECTORY = ROOT_DIRECTORY / "content"
SOURCES_DIRECTORY = CONTENT_DIRECTORY / "sources"

SHM_DIRECTORY = SOURCES_DIRECTORY / "shm"

PROGRAMS = {
    "camera": SOURCES_DIRECTORY / "camera" / "main_camera.py",
    "stepper": SOURCES_DIRECTORY / "stepper" / "main_stepper.py",
    "interface": SOURCES_DIRECTORY / "interface" / "main_interface.py",
}

# Active child processes
processes = []

# Indicates whether SHM initialization succeeded
shm_initialized = False


# Make the sources directory importable.
# This allows child programs to import the shm package and their sibling packages.
if str(SOURCES_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCES_DIRECTORY))

from shm.shm_manager import _initialize, _unlink_all


# SECTION 2 : SHARED MEMORY INITIALIZATION

def initialize_shm():
    """
    Initialize shared memory directly from the main process.
    No separate SHM launcher process is required.
    """

    global shm_initialized

    print("\n[MAIN] Initializing shared memory...")

    if not SHM_DIRECTORY.is_dir():
        raise FileNotFoundError(f"SHM directory not found: {SHM_DIRECTORY}")

    _initialize()

    shm_initialized = True

    print("[MAIN] Shared memory initialized successfully.\n")


# SECTION 3 : PROGRAM LAUNCHING

def launch_program(name):
    """
    Launch a registered program as an independent process.
    """

    name = name.lower().removesuffix(".py")

    if name not in PROGRAMS:
        raise ValueError(f"Unknown program: {name}")

    script = PROGRAMS[name]

    if not script.is_file():
        raise FileNotFoundError(f"Program script not found: {script}")

    print(f"[MAIN] Launching {name}...")

    # Ensure child processes can import packages from sources.
    environment = os.environ.copy()

    existing_pythonpath = environment.get("PYTHONPATH", "")

    environment["PYTHONPATH"] = (str(SOURCES_DIRECTORY) + os.pathsep + existing_pythonpath)

    process = subprocess.Popen([sys.executable, str(script)], cwd=SOURCES_DIRECTORY, env=environment)

    processes.append((name, process))

    print(f"[MAIN] {name} launched (PID: {process.pid})")


# SECTION 4 : PROCESS MONITORING


def monitor():
    """
    Monitor all child processes.
    Returns as soon as one program terminates.
    """

    print("\n[MAIN] All programs are running.")
    print("[MAIN] Press CTRL+C to stop all programs.\n")

    while True:
        for name, process in processes:
            return_code = process.poll()

            if return_code is not None:
                print(f"[MAIN] {name} terminated (exit code: {return_code}).")

                return

        time.sleep(0.2)


# SECTION 5 : PROCESS SHUTDOWN

def stop_all():
    """
    Stop all active child processes.
    First requests graceful termination, then forces termination if a process does not respond.
    """

    if not processes:
        return

    print("\n[MAIN] Stopping all programs...")

    # Request termination of every active process.
    for name, process in processes:
        if process.poll() is None:
            print(f"[MAIN] Stopping {name}...")

            process.terminate()

    # Wait for termination, with a timeout.
    for name, process in processes:
        try:
            process.wait(timeout=5)

        except subprocess.TimeoutExpired:

            print(f"[MAIN] Forcing termination of {name}...")

            process.kill()
            process.wait()

    print("[MAIN] All programs have been stopped.")


# SECTION 6 : SHARED MEMORY CLEANUP

def cleanup_shm():
    """
    Remove shared memory after all child processes have terminated.
    """

    global shm_initialized

    if not shm_initialized:
        return

    print("\n[MAIN] Cleaning shared memory...")

    try:
        _unlink_all()

        shm_initialized = False

        print("[MAIN] Shared memory cleaned successfully.")

    except Exception as error:
        print(f"[MAIN] SHM cleanup error: {error}")

        raise


# SECTION 7 : MAIN EXECUTION

def main():
    parser = argparse.ArgumentParser(description="Central manager for project programs.")

    parser.add_argument("programs", nargs="+", help="Programs to launch: camera, stepper, interface")

    args = parser.parse_args()

    try:
        # Initialize shared memory
        initialize_shm()

        # Launch requested programs
        for name in args.programs:
            launch_program(name)

        # Monitor their execution
        monitor()

    except KeyboardInterrupt:
        print("\n[MAIN] User interruption detected.")

    except Exception as error:
        print(f"\n[MAIN] ERROR: {error}")

    finally:
        # Stop all child processes first
        stop_all()

        # Remove shared memory only after children stop
        cleanup_shm()


if __name__ == "__main__":
    main()
