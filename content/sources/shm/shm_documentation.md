# Documentation technique — SHM
**Projet : Auto-Pos**

# 0. Pourquoi utiliser du SHM dans le projet ?

Le projet Auto-Pos repose sur plusieurs processus indépendants, notamment :
- Le traitement des images de la caméra.
- Le contrôle des steppers.
- La gestion de l'interface utilisateur.

Ces processus doivent pouvoir échanger des données en temps réel sans être directement dépendants les uns des autres.

Le **Shared Memory (SHM)** permet de mettre à disposition une zone mémoire commune à plusieurs processus. Chaque processus peut ainsi lire et écrire les données nécessaires à son fonctionnement.

### Avantages dans le projet

- **Communication centralisée :** tous les processus utilisent une même source de données.
- **Faible latence :** les données sont accessibles directement depuis la mémoire partagée, sans passer par un échange réseau ou une communication par messages.
- **Échange de données volumineuses :** possibilité de transmettre des images ou d'autres données binaires.
- **Découplage des modules :** chaque programme utilise le SHM sans avoir besoin de connaître l'implémentation interne des autres programmes.
- **Synchronisation :** les verrous permettent de contrôler les accès concurrents aux variables partagées.

**Choix technique :** la mémoire partagée a été retenue pour centraliser les échanges interprocessus, limiter les coûts de communication et faciliter l'intégration indépendante des différents modules.

## 1. Structure du projet

### 1.1 Organisation des fichiers

| Fichier | Fonction |
|---|---|
| `shm_config.py` | Configuration des variables partagées |
| `shm_manager.py` | Gestion des segments de mémoire partagée |
| `camera_to_shm_header.py` | Interface SHM de la caméra |
| `stepper_to_shm_header.py` | Interface SHM des steppers |
| `interface_to_shm_header.py` | Interface SHM de l'interface |
| `main.py` | Initialisation, lancement des processus et nettoyage |

### 1.2 Architecture

- `main.py` initialise la mémoire partagée.
- `shm_manager.py` crée et gère les segments.
- Chaque module utilise son propre fichier d'interface pour accéder aux variables partagées.
- Le processus principal est responsable de la suppression des segments.

---

## 2. Configuration — `shm_config.py`

### 2.1 Déclaration des variables

Les variables partagées sont définies dans le dictionnaire `SHARED_VARIABLES`.

Structure d'une déclaration :

```python
SHARED_VARIABLES = {
    "variable_name": {
        "initial_value": None,
        "size": DEFAULT_SHM_SIZE,
    },
}
```

| Paramètre | Description |
|---|---|
| `variable_name` | Identifiant de la variable partagée |
| `initial_value` | Valeur écrite lors de l'initialisation |
| `size` | Capacité du segment en octets |

### 2.2 Exemple

```python
SHARED_VARIABLES = {
    "temperature": {
        "initial_value": 0.0,
        "size": DEFAULT_SHM_SIZE,
    },
    "camera_image": {
        "initial_value": None,
        "size": 10 * DEFAULT_SHM_SIZE,
    },
}
```

La taille doit être adaptée au volume maximal des données à stocker.

**Attention :** la taille du segment doit inclure l'en-tête de 8 octets et les éventuels frais supplémentaires liés à la sérialisation.

---

## 3. Gestionnaire — `shm_manager.py`

### 3.1 Dépendances

| Module | Utilisation |
|---|---|
| `multiprocessing.shared_memory` | Création et accès aux segments SHM |
| `pickle` | Sérialisation et désérialisation des données |
| `struct` | Encodage de la taille des données |
| `hashlib` | Génération des noms de segments et des fichiers de verrouillage |
| `filelock` | Synchronisation des accès |
| `os`, `tempfile` | Gestion des processus et des fichiers temporaires |

### 3.2 Nommage des segments

Chaque variable possède un segment SHM distinct.

Le nom est généré à partir du nom de la variable :

```python
digest = hashlib.sha256(variable.encode("utf-8")).hexdigest()[:16]

name = SHM_PREFIX + digest
```

Cela permet d'obtenir un nom de segment déterministe, sans utiliser directement le nom de la variable.

### 3.3 Sérialisation

Les données sont converties en bytes avec `pickle` avant leur écriture.

```python
data = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
```

Lors de la lecture, les bytes sont reconvertis en objet Python :

```python
value = pickle.loads(data)
```

Le gestionnaire peut ainsi stocker différents types d'objets Python, sous réserve que leur sérialisation soit possible et que leur taille respecte la capacité du segment.

### 3.4 Structure d'un segment

Chaque segment est organisé de la manière suivante :

| Zone | Taille | Contenu |
|---|---:|---|
| En-tête | 8 octets | Taille des données sérialisées |
| Données | Variable | Objet sérialisé avec `pickle` |

La constante utilisée est :

```python
HEADER_SIZE = 8
```

L'en-tête utilise un entier non signé de 64 bits, encodé en little-endian :

```python
struct.pack("<Q", len(data))
struct.unpack("<Q", shm.buf[:HEADER_SIZE])
```

La taille enregistrée permet au processus lecteur de déterminer précisément le nombre d'octets à récupérer.

### 3.5 Synchronisation

Chaque variable possède son propre fichier de verrouillage.

Les fichiers sont stockés dans :

```python
LOCK_DIRECTORY = os.path.join(tempfile.gettempdir(), "physproj_locks")
```

Les opérations de lecture et d'écriture sont protégées par `FileLock`.

```python
with _lock(variable):
    # SHM operation
```

Le verrou est :
- Bloquant : le processus attend sa disponibilité.
- Spécifique à une variable : les opérations sur des variables différentes peuvent s'effectuer indépendamment.
- Utilisé aussi bien en lecture qu'en écriture.

### 3.6 Gestion des processus

Le PID du processus courant est mémorisé :

```python
_current_pid = os.getpid()
```

La fonction `_check_process()` vérifie si le processus a changé.

En cas de changement, notamment après un `fork`, les connexions SHM héritées sont fermées et le cache local est réinitialisé.

Cela évite de réutiliser des connexions ouvertes par un autre processus.

---

## 4. Fonctions du gestionnaire

Les fonctions internes du gestionnaire sont les suivantes :

| Fonction | Rôle |
|---|---|
| `_initialize()` | Crée et initialise tous les segments déclarés |
| `_attach(variable)` | Ouvre une connexion vers un segment existant |
| `_read(variable)` | Lit et désérialise une variable |
| `_write(variable, value)` | Sérialise et écrit une variable |
| `_close_all()` | Ferme les connexions locales |
| `_unlink_all()` | Supprime les segments créés par le processus principal |

### 4.1 Initialisation — `_initialize()`

- Vérifie l'état du gestionnaire.
- Crée le dossier des verrous.
- Crée un segment pour chaque variable déclarée.
- Sérialise et écrit la valeur initiale.
- Enregistre les segments créés pour permettre leur suppression ultérieure.

Une erreur pendant l'initialisation entraîne le nettoyage des segments créés pendant cette tentative.

### 4.2 Lecture — `_read(variable)`

1. Vérifie que la variable est déclarée.
2. Acquiert son verrou.
3. Ouvre le segment si nécessaire.
4. Lit la taille depuis l'en-tête.
5. Vérifie que cette taille est valide.
6. Récupère les données.
7. Désérialise et retourne la valeur.

### 4.3 Écriture — `_write(variable, value)`

1. Vérifie que la variable est déclarée.
2. Sérialise la valeur.
3. Acquiert le verrou.
4. Ouvre le segment si nécessaire.
5. Vérifie que la donnée tient dans le segment.
6. Écrit les données.
7. Met à jour l'en-tête avec la nouvelle taille.

### 4.4 Fermeture et suppression

Deux opérations distinctes sont utilisées :

| Opération | Fonction | Effet |
|---|---|---|
| Fermeture | `_close_all()` | Ferme les connexions du processus |
| Suppression | `_unlink_all()` | Supprime les segments SHM |

`_close_all()` ne supprime pas les segments.

`_unlink_all()` doit être appelé uniquement par le processus principal, après la terminaison des processus enfants.

---

## 5. Interface des modules

### 5.1 Principe

Chaque module dispose d'un fichier d'interface dédié.

Ces fichiers fournissent des fonctions simplifiées pour accéder aux variables partagées.

L'objectif est de ne pas exposer directement les fonctions internes de `shm_manager.py` aux programmes utilisateurs.

### 5.2 Fonctions d'accès

L'interface repose sur deux opérations :

| Fonction | Rôle |
|---|---|
| `get(variable)` | Récupère la valeur d'une variable |
| `set(variable, value)` | Modifie la valeur d'une variable |

Exemple d'utilisation :

```python
import camera_to_shm_header as shm

shm.set("temperature", 25.5)

temperature = shm.get("temperature")
```

Les noms de variables utilisés doivent correspondre à ceux déclarés dans `SHARED_VARIABLES`.

---

## 6. Gestion des images

### 6.1 Principe

Les images sont stockées sous forme de bytes afin de pouvoir être sérialisées et transférées dans le SHM.

Avec OpenCV, l'image est d'abord encodée au format JPEG.

### 6.2 Écriture

```python
success, encoded_image = cv2.imencode(".jpg", image)

if success:
    shm.set("camera_image", encoded_image.tobytes())
```

### 6.3 Lecture

```python
image_data = shm.get("camera_image")

image_received = cv2.imdecode(np.frombuffer(image_data, dtype=np.uint8), cv2.IMREAD_COLOR)
```

### 6.4 Dimensionnement

La capacité du segment doit être suffisante pour contenir les données sérialisées.

Pour une image, la taille dépend notamment :
- De sa résolution.
- Du format de compression.
- De son contenu.

Une erreur `ValueError` est levée lorsque les données dépassent la capacité disponible.

---

## 7. Cycle de vie du SHM

### 7.1 Ordre d'exécution

```text
main.py
  |
  v
_initialize()
  |
  v
Lancement des processus enfants
  |
  v
Utilisation du SHM
  |
  v
Arrêt des processus enfants
  |
  v
_unlink_all()
  |
  v
Fin du programme
```

### 7.2 Règles d'utilisation

- Initialiser le SHM avant de lancer les processus enfants.
- Déclarer toutes les variables dans `SHARED_VARIABLES`.
- Ne pas créer manuellement de segments depuis les modules utilisateurs.
- Utiliser les fonctions `get()` et `set()` des interfaces.
- Ne pas appeler `_unlink_all()` depuis un processus enfant.
- Attendre la terminaison des processus enfants avant de supprimer les segments.

---

## 8. Gestion des erreurs

| Erreur | Cause possible |
|---|---|
| `KeyError` | Variable non déclarée dans `SHARED_VARIABLES` |
| `FileExistsError` | Segment portant déjà le nom attendu |
| `RuntimeError` | Segment déjà initialisé ou taille de données invalide |
| `ValueError` | Donnée trop volumineuse pour le segment |
| `FileNotFoundError` | Segment SHM inexistant lors de la connexion |

**Remarque :** les objets stockés avec `pickle` doivent provenir de processus de confiance. La désérialisation de données non fiables peut exécuter du code arbitraire.