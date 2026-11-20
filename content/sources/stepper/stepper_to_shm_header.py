"""
stepper_to_shm_header.py

Interface de communication entre les programmes.

Les variables ci-dessous sont des EXEMPLES.
Chacun doit y déclarer ses propres variables globales destinées à être échangées avec les autres programmes.

Plus tard on se chargera de ne modifier que les fonctions en bas du fichier pour communiquer avec le shm.
"""

from pathlib import Path
import sys

# SECTION 0 : SHM Interface Import

SHM_DIRECTORY = (Path(__file__).resolve().parent.parent / "shm")
sys.path.insert(0, str(SHM_DIRECTORY))

from shared_state import SharedState

# SECTION 1 : VARIABLES QUI SERONT A PARTAGER (EXEMPLES)

stepper_value = True

current_location = 15

target_location = 190


# SECTION 2 : Fonctions à accès (pour l'instant en local et plus tard au shm)

def get(nom_variable):
    """Retourne la valeur d'une variable globale."""

    if nom_variable not in globals():
        raise NameError(f"Variable inconnue : {nom_variable}")

    return globals()[nom_variable]


def set(nom_variable, new_value):
    """Modifie la valeur d'une variable globale."""

    if nom_variable not in globals():
        raise NameError(f"Variable inconnue : {nom_variable}")

    globals()[nom_variable] = new_value