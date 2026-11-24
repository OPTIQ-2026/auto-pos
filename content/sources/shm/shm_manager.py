import os
import pickle
import hashlib
import struct
import inspect
import tempfile

from multiprocessing import shared_memory
from filelock import FileLock

from .shm_config import SHARED_VARIABLES, SHM_PREFIX


HEADER_SIZE = 8

LOCK_DIRECTORY = os.path.join(
    tempfile.gettempdir(),
    "physproj_locks"
)

_connections = {}
_created = {}

# Permet de détecter un changement de processus
_current_pid = os.getpid()


def _open_shared_memory(**kwargs):
    """
    Python 3.13+ accepte track=False.
    Sur les versions antérieures, ce paramètre n'existe pas.
    """

    if "track" in inspect.signature(
        shared_memory.SharedMemory
    ).parameters:
        kwargs["track"] = False

    return shared_memory.SharedMemory(**kwargs)


def _shm_name(variable):
    digest = hashlib.sha256(
        variable.encode("utf-8")
    ).hexdigest()[:16]

    return SHM_PREFIX + digest


def _lock_path(variable):
    digest = hashlib.sha256(
        variable.encode("utf-8")
    ).hexdigest()

    return os.path.join(
        LOCK_DIRECTORY,
        digest + ".lock"
    )


def _lock(variable):
    os.makedirs(LOCK_DIRECTORY, exist_ok=True)

    # Verrou bloquant, indépendant du système d'exploitation
    return FileLock(_lock_path(variable))


def _check_process():
    """
    Si le processus a changé (fork), on ferme ses connexions héritées et on repart avec un cache vide.
    """

    global _current_pid

    pid = os.getpid()

    if pid != _current_pid:

        for shm in list(_connections.values()):
            try:
                shm.close()
            except Exception:
                pass

        _connections.clear()
        _current_pid = pid


def _check_variable(variable):

    if variable not in SHARED_VARIABLES:
        raise KeyError(
            f"Variable '{variable}' non déclarée "
            "dans SHARED_VARIABLES."
        )


def _attach(variable):

    _check_process()
    _check_variable(variable)

    if variable not in _connections:

        _connections[variable] = _open_shared_memory(
            name=_shm_name(variable),
            create=False
        )

    return _connections[variable]


def _initialize():
    """
    Initialise tous les segments partagés.
    À appeler une seule fois dans le processus principal, avant de lancer les processus enfants.
    """

    _check_process()

    if _created:
        raise RuntimeError(
            "La mémoire partagée est déjà initialisée."
        )

    os.makedirs(LOCK_DIRECTORY, exist_ok=True)

    try:

        for variable, config in SHARED_VARIABLES.items():

            with _lock(variable):

                try:
                    shm = _open_shared_memory(
                        name=_shm_name(variable),
                        create=True,
                        size=config["size"]
                    )

                except FileExistsError:
                    raise RuntimeError(
                        f"Le segment '{_shm_name(variable)}' "
                        "existe déjà. Une ancienne instance "
                        "est peut-être encore active."
                    )

                _connections[variable] = shm
                _created[variable] = shm.name

                data = pickle.dumps(
                    config["initial_value"],
                    protocol=pickle.HIGHEST_PROTOCOL
                )

                if len(data) + HEADER_SIZE > shm.size:
                    raise ValueError(
                        f"Valeur initiale trop volumineuse : "
                        f"{variable}"
                    )

                shm.buf[:HEADER_SIZE] = struct.pack(
                    "<Q", len(data)
                )

                shm.buf[
                    HEADER_SIZE:HEADER_SIZE + len(data)
                ] = data

    except Exception:

        # Nettoyage des segments créés pendant cette tentative
        _unlink_all()
        raise


def _read(variable):
    """
    Lecture exclusive d'une variable partagée.
    """

    _check_variable(variable)

    with _lock(variable):

        shm = _attach(variable)

        data_size = struct.unpack(
            "<Q",
            shm.buf[:HEADER_SIZE]
        )[0]

        if data_size > shm.size - HEADER_SIZE:
            raise RuntimeError(
                f"Taille invalide pour '{variable}'."
            )

        data = bytes(
            shm.buf[
                HEADER_SIZE:HEADER_SIZE + data_size
            ]
        )

        return pickle.loads(data)


def _write(variable, value):
    """
    Écriture exclusive d'une variable partagée.
    """

    _check_variable(variable)

    data = pickle.dumps(
        value,
        protocol=pickle.HIGHEST_PROTOCOL
    )

    with _lock(variable):

        shm = _attach(variable)

        if len(data) + HEADER_SIZE > shm.size:
            raise ValueError(
                f"Donnée trop volumineuse pour '{variable}'. "
                f"Taille nécessaire : {len(data) + HEADER_SIZE} "
                f"octets ; taille disponible : {shm.size} octets."
            )

        shm.buf[
            HEADER_SIZE:HEADER_SIZE + len(data)
        ] = data

        shm.buf[:HEADER_SIZE] = struct.pack(
            "<Q", len(data)
        )


def _close_all():

    _check_process()

    for shm in list(_connections.values()):
        shm.close()

    _connections.clear()


def _unlink_all():
    """
    À appeler uniquement par le processus principal,
    lorsque tous les processus enfants sont terminés.
    """

    _check_process()

    for variable, name in list(_created.items()):

        with _lock(variable):

            shm = _connections.get(variable)
            temporary_connection = False

            if shm is None:
                shm = _open_shared_memory(
                    name=name,
                    create=False
                )
                temporary_connection = True

            try:
                shm.unlink()

            finally:
                if temporary_connection:
                    shm.close()

    _created.clear()

    _close_all()
