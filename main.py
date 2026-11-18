
import argparse
import subprocess
import sys
import time
from pathlib import Path


# ============================================================
# SECTION : Project Configuration & Program Registry
# ============================================================

# Define the project root directory and source locations.
ROOT_DIRECTORY = Path(__file__).resolve().parent
CONTENT_DIRECTORY = ROOT_DIRECTORY / "content"
SOURCES_DIRECTORY = CONTENT_DIRECTORY / "sources"

# Define the shared memory initialization script.
SHM_DIRECTORY = SOURCES_DIRECTORY / "shm"
SHM_LAUNCHER = SHM_DIRECTORY / "launch_shm.py"

# Register the available programs and their corresponding scripts.
PROGRAMS = {
    "camera": SOURCES_DIRECTORY / "camera" / "camera.py",
    "stepper": SOURCES_DIRECTORY / "stepper" / "stage.py",
    "interface": SOURCES_DIRECTORY / "interface" / "interface.py",
}

# Store references to all active child processes.
processes = []


# ============================================================
# SECTION : SHM Initialization & Setup
# ============================================================

def initialize_shm():
    """
    Initialize the shared memory before launching any program.

    Executes the dedicated SHM initialization script as a separate
    process and waits for its completion.

    Raises a FileNotFoundError if the initialization script
    cannot be located, or a RuntimeError if initialization fails.
    """

    print("\n[MAIN] Initializing shared memory...")

    # Validate the existence of the SHM initialization script.
    if not SHM_LAUNCHER.is_file():
        raise FileNotFoundError(
            f"SHM initialization script not found: {SHM_LAUNCHER}"
        )

    # Execute the initialization script and wait for completion.
    result = subprocess.run(
        [sys.executable, str(SHM_LAUNCHER)],
        cwd=SHM_DIRECTORY
    )

    # Validate the initialization process exit status.
    if result.returncode != 0:
        raise RuntimeError(
            "Shared memory initialization failed."
        )

    print("[MAIN] Shared memory initialized successfully.\n")


# ============================================================
# SECTION : Program Launching & Process Registration
# ============================================================

def launch_program(name):
    """
    Launch a registered Python program as an independent process.

    Resolves the requested program name, validates its script path
    and starts a new Python interpreter using subprocess.Popen.

    Stores the resulting process reference for subsequent
    monitoring and lifecycle management.
    """

    # Normalize the requested program name.
    name = name.lower().removesuffix(".py")

    # Validate the requested program against the registry.
    if name not in PROGRAMS:
        raise ValueError(f"Unknown program: {name}")

    script = PROGRAMS[name]

    # Validate the existence of the requested Python script.
    if not script.is_file():
        raise FileNotFoundError(
            f"Program script not found: {script}"
        )

    print(f"[MAIN] Launching {name}...")

    # Start the program in an independent Python process.
    process = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=script.parent
    )

    # Register the process for subsequent monitoring.
    processes.append((name, process))

    print(f"[MAIN] {name} launched (PID: {process.pid})")


# ============================================================
# SECTION : Process Monitoring & Synchronization
# ============================================================

def monitor():
    """
    Monitor all registered child processes.

    Periodically checks the execution status of every process.

    Returns when one of the programs terminates, allowing the
    main execution flow to initiate a coordinated shutdown.
    """

    print("\n[MAIN] All programs are running.")
    print("[MAIN] Press CTRL+C to stop all programs.\n")

    while True:

        # Check the execution status of every registered process.
        for name, process in processes:

            return_code = process.poll()

            # Detect unexpected or normal process termination.
            if return_code is not None:
                print(
                    f"[MAIN] {name} terminated "
                    f"(exit code: {return_code})."
                )

                return

        # Avoid continuous polling and unnecessary CPU usage.
        time.sleep(0.2)


# ============================================================
# SECTION : Process Lifecycle & Teardown
# ============================================================

def stop_all():
    """
    Stop all registered child processes.

    First requests a graceful termination for every active process.

    Waits for each process to exit and forcibly terminates any
    process that does not respond within the allocated timeout.

    Does not destroy the shared memory segment, as its lifecycle
    remains independent from the child process management.
    """

    if not processes:
        return

    print("\n[MAIN] Stopping all programs...")

    # Request graceful termination of all active processes.
    for name, process in processes:

        if process.poll() is None:
            print(f"[MAIN] Stopping {name}...")
            process.terminate()

    # Wait for process termination and enforce the timeout.
    for name, process in processes:

        if process.poll() is None:

            try:
                process.wait(timeout=5)

            except subprocess.TimeoutExpired:

                print(f"[MAIN] Forcing termination of {name}...")

                process.kill()
                process.wait()

    print("[MAIN] All programs have been stopped.")


# ============================================================
# SECTION : Main Execution & Command-Line Interface
# ============================================================

def main():
    """
    Execute the central program manager.

    Parses the requested programs from command-line arguments,
    initializes shared memory, launches the selected programs
    and monitors their execution.

    Ensures that all child processes are stopped when the main
    execution ends, whether normally or following an exception.
    """

    # Configure the command-line argument parser.
    parser = argparse.ArgumentParser(
        description="Central manager for project programs."
    )

    # Accept one or multiple program names.
    parser.add_argument(
        "programs",
        nargs="+",
        help="Programs to launch: camera, stepper, interface"
    )

    args = parser.parse_args()

    try:

        # Initialize shared memory before launching any program.
        initialize_shm()

        # Launch all requested programs.
        for name in args.programs:
            launch_program(name)

        # Monitor the execution of all active processes.
        monitor()

    except KeyboardInterrupt:

        # Handle user interruption through CTRL+C.
        print("\n[MAIN] User interruption detected.")

    except Exception as error:

        # Report execution errors.
        print(f"\n[MAIN] ERROR: {error}")

    finally:

        # Ensure coordinated termination of all child processes.
        stop_all()


if __name__ == "__main__":
    main()
