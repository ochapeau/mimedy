# 🗂️ mimedy

[![CI](https://github.com/ochapeau/mimedy/actions/workflows/ci.yml/badge.svg)](https://github.com/ochapeau/mimedy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mimedy)](https://pypi.org/project/mimedy/)
[![Python](https://img.shields.io/pypi/pyversions/mimedy)](https://pypi.org/project/mimedy/)

**Range un dossier en désordre selon le vrai type de chaque fichier, pas selon son extension.**\
**Tidies up a messy folder by each file's real type, not by its extension.**

*mimedy = **MIME** + **tidy** (ranger) : le type MIME de chaque fichier décide de sa place.*\
*mimedy = **MIME** + **tidy**: each file's MIME type decides where it belongs.*

[Français](#français) · [English](#english)

---

<a id="français"></a>

## 🇫🇷 Français

### Pourquoi ?

Un dossier `Téléchargements` finit toujours par ressembler à ça : des PDF, des captures d'écran, des archives, un `.json` exporté un jour, un fichier sans extension dont personne ne se souvient…

La plupart des outils de rangement se fient à l'extension. Or une extension peut mentir, manquer ou être fausse. **mimedy** utilise [Magika](https://github.com/google/magika), le modèle de deep learning de Google qui identifie un fichier **à partir de son contenu**, pour décider où il doit aller.

```text
$ mimedy ~/Downloads
[INFO] Loaded config from /Users/me/.config/mimedy/config.yaml
[INFO] Organizing /Users/me/Downloads
[INFO] 'export.csv' → Data/
[INFO] 'holidays.jpg' → Photos/
[INFO] 'invoice' → PDF/
[INFO] 'report.pdf' → PDF/report (1).pdf
[INFO] 'script.py' → Python/
[WARNING] Skipped 'locked.txt': Magika could not read the file (permission_error)
[INFO] 5 files to move into 4 folders, 1 skipped
Move 5 files? [y/N]: y
[INFO] Done: 5 moved, 0 failed
```

### Fonctionnalités

- 🧠 **Détection par le contenu** : Magika reconnaît plus de 200 types de fichiers, même renommés ou sans extension.
- 🔒 **100 % local** : le modèle d'IA est livré avec l'outil et tourne sur votre machine. Aucune connexion réseau, aucun fichier ni aucune donnée n'est envoyé où que ce soit.
- 🪜 **Règles en cascade** : fichiers cachés, fichiers volumineux, extensions, types MIME, puis le groupe Magika en dernier recours.
- 📋 **Plan puis confirmation** : tous les déplacements sont affichés avant d'être effectués, et rien ne bouge sans votre accord. `--dry-run` s'arrête au plan.
- 🧯 **Robuste** : un fichier illisible ou verrouillé est signalé et ignoré, sans interrompre le rangement.
- 🛡️ **Aucun écrasement** : si `photo.jpg` existe déjà, le nouveau fichier devient `photo (1).jpg`.
- 🐛 **Mode `--verbose`** : indique pour chaque fichier la règle qui a décidé de sa destination.
- ⚙️ **Configuration YAML** simple, entièrement facultative.

### Installation

mimedy est publié sur [PyPI](https://pypi.org/project/mimedy/) et nécessite Python 3.10+. Le plus simple est de l'installer comme outil isolé avec [uv](https://docs.astral.sh/uv/) ou [pipx](https://pipx.pypa.io/) :

```bash
uv tool install mimedy     # ou : pipx install mimedy
```

Pour l'essayer sans rien installer :

```bash
uvx mimedy ~/Downloads --dry-run
```

### Utilisation

> 💡 mimedy affiche toujours le plan complet et demande confirmation avant de déplacer quoi que ce soit.

```bash
# Afficher le plan, puis confirmer
mimedy ~/Downloads

# Afficher le plan seulement
mimedy ~/Downloads --dry-run

# Sans confirmation, par exemple dans un script
mimedy ~/Downloads --yes --config my-config.yaml

# Comprendre pourquoi un fichier va à tel endroit
mimedy ~/Downloads --dry-run --verbose
```

| Option | Description |
| :--- | :--- |
| `DIRECTORY` | Dossier à ranger *(obligatoire)*. |
| `--config`, `-c PATH` | Fichier de configuration YAML *(par défaut : voir [Configuration](#configuration))*. |
| `--dry-run`, `-n` | Affiche les déplacements prévus sans les effectuer. |
| `--yes`, `-y` | Déplace sans demander de confirmation. |
| `--verbose`, `-v` | Affiche la règle appliquée à chaque fichier. |
| `--lowercase`, `-l` | Garde en minuscules les dossiers nommés d'après Magika (`video/` au lieu de `Video/`). |
| `--version`, `-V` | Affiche la version. |
| `--help`, `-h` | Affiche l'aide. |
| `--init-config` | Crée une configuration d'exemple commentée à l'emplacement par défaut (sans jamais écraser une configuration existante). |
| `--install-completion` | Active l'autocomplétion des options avec Tab dans votre shell (une seule fois suffit). |

Seuls les fichiers situés directement dans le dossier sont traités. Les sous-dossiers existants ne sont pas touchés, ce qui permet de relancer l'outil sans risque.

| Code de sortie | Signification |
| :-: | :--- |
| `0` | Tout s'est bien passé, ou il n'y avait rien à ranger. |
| `1` | Au moins un fichier n'a pas pu être traité, ou la confirmation a été refusée. |
| `2` | Arguments ou configuration invalides. |

### Configuration

Sans `--config`, mimedy lit le fichier de configuration personnel, s'il existe :

| Système | Emplacement |
|---|---|
| Linux, macOS | `~/.config/mimedy/config.yaml` (ou `$XDG_CONFIG_HOME/mimedy/config.yaml`) |
| Windows | `%APPDATA%\mimedy\config.yaml` |

S'il n'existe pas, les valeurs par défaut sont utilisées. Un fichier passé avec `--config` doit en revanche exister. `mimedy --help` affiche l'emplacement exact sur votre machine.

Pour démarrer, créez une configuration d'exemple commentée, puis adaptez-la :

```bash
mimedy --init-config
# Created config file: /Users/me/.config/mimedy/config.yaml
```

```yaml
hidden: "Hidden"            # fichiers commençant par '.'

large_files:
  threshold_mb: 500         # en Mo décimaux, comme le Finder ou l'Explorateur
  target_dir: "Large"

extensions:                 # correspondance exacte sur l'extension
  .blend: "Blender"
  .csv: "Data"

mimetypes:                  # type MIME détecté par Magika
  application/pdf: "PDF"
  image/jpeg: "Photos"
```

Toutes les clés sont facultatives : celles qui manquent reprennent leur valeur par défaut. Les destinations peuvent contenir des sous-dossiers (`"Code/Python"`). [`config.example.yaml`](src/mimedy/config.example.yaml), le fichier copié par `--init-config`, contient un exemple complet et commenté.

### Comment un fichier est-il classé ?

Les règles sont évaluées dans cet ordre ; **la première qui correspond l'emporte** :

| # | Règle | Exemple |
|:-:|:---|:---|
| 1 | Fichier caché | `.env` → `Hidden/` |
| 2 | Fichier volumineux | `film.mkv` (2 Go) → `Large/` |
| 3 | Extension | `scene.blend` → `Blender/` |
| 4 | Type MIME (Magika) | `facture` *(PDF sans extension)* → `PDF/` |
| 5 | Groupe Magika | `script.py` → `Code/` |

Les règles 1 à 3 ne lisent pas le contenu des fichiers : elles sont instantanées. Magika n'est appelé que si elles ne suffisent pas.

### Structure du projet

```text
mimedy/
├── pyproject.toml
├── src/mimedy/
│   ├── main.py              # Point d'entrée de la CLI (Typer)
│   ├── config.py            # Chargement et validation de la configuration
│   ├── config.example.yaml  # Configuration d'exemple commentée
│   ├── organizer.py         # Règles de classement, planification et déplacements
│   └── errors.py            # Exceptions du projet
└── tests/                   # Tests pytest (configuration, règles, plan, CLI)
```

### Développement

Le code est vérifié par [Ruff](https://docs.astral.sh/ruff/) (lint et formatage) à chaque commit, et testé avec [pytest](https://docs.pytest.org/). L'intégration continue lance les deux à chaque push, sur Python 3.10 à 3.13.

```bash
git clone https://github.com/ochapeau/mimedy.git
cd mimedy
uv sync                     # crée l'environnement de développement
uv run pre-commit install   # vérifications automatiques à chaque commit
uv run pytest               # lancer les tests
uv run mimedy --help        # lancer la version en cours de développement
```

### Feuille de route

- [x] Configuration typée et validée
- [x] Configuration globale dans `~/.config/mimedy/`
- [x] Tests automatisés et intégration continue
- [x] Publication sur PyPI (`uv tool install mimedy`)
- [ ] Ignorer les fichiers système (`.DS_Store`, `.localized`, `Thumbs.db`, `desktop.ini`…), avec une option pour les ranger quand même
- [ ] Motifs de fichiers à ignorer (téléchargements en cours : `*.part`, `*.crdownload`…)
- [ ] Annuler le dernier rangement (`--undo`)
- [ ] Interface en terminal (TUI), en option

### Licence

Distribué sous licence MIT. Voir [LICENSE](LICENSE).

---

<a id="english"></a>

## 🇬🇧 English

### Why?

A `Downloads` folder always ends up looking the same: PDFs, screenshots, archives, a `.json` exported at some point, a file with no extension that nobody remembers…

Most organizing tools trust file extensions. But an extension can lie, be missing, or simply be wrong. **mimedy** uses [Magika](https://github.com/google/magika), Google's deep learning model that identifies a file **from its content**, to decide where it belongs.

```text
$ mimedy ~/Downloads
[INFO] Loaded config from /Users/me/.config/mimedy/config.yaml
[INFO] Organizing /Users/me/Downloads
[INFO] 'export.csv' → Data/
[INFO] 'holidays.jpg' → Photos/
[INFO] 'invoice' → PDF/
[INFO] 'report.pdf' → PDF/report (1).pdf
[INFO] 'script.py' → Python/
[WARNING] Skipped 'locked.txt': Magika could not read the file (permission_error)
[INFO] 5 files to move into 4 folders, 1 skipped
Move 5 files? [y/N]: y
[INFO] Done: 5 moved, 0 failed
```

### Features

- 🧠 **Content-based detection**: Magika recognizes over 200 file types, even when renamed or missing an extension.
- 🔒 **100% local**: the AI model ships with the tool and runs on your machine. No network connection, no file or data is ever sent anywhere.
- 🪜 **Cascading rules**: hidden files, large files, extensions, MIME types, then the Magika group as a fallback.
- 📋 **Plan, then confirm**: every move is shown before it happens, and nothing moves without your approval. `--dry-run` stops at the plan.
- 🧯 **Robust**: an unreadable or locked file is reported and skipped, without stopping the run.
- 🛡️ **Never overwrites**: if `photo.jpg` already exists, the new file becomes `photo (1).jpg`.
- 🐛 **`--verbose` mode**: shows which rule decided each file's destination.
- ⚙️ **Simple YAML configuration**, entirely optional.

### Installation

mimedy is published on [PyPI](https://pypi.org/project/mimedy/) and requires Python 3.10+. The easiest way is to install it as an isolated tool with [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/):

```bash
uv tool install mimedy     # or: pipx install mimedy
```

To try it without installing anything:

```bash
uvx mimedy ~/Downloads --dry-run
```

### Usage

> 💡 mimedy always shows the full plan and asks for confirmation before moving anything.

```bash
# Show the plan, then confirm
mimedy ~/Downloads

# Only show the plan
mimedy ~/Downloads --dry-run

# No confirmation, e.g. in a script
mimedy ~/Downloads --yes --config my-config.yaml

# Understand why a file goes where it goes
mimedy ~/Downloads --dry-run --verbose
```

| Option | Description |
| :--- | :--- |
| `DIRECTORY` | Folder to organize *(required)*. |
| `--config`, `-c PATH` | YAML configuration file *(default: see [Configuration](#configuration-1))*. |
| `--dry-run`, `-n` | Show planned moves without performing them. |
| `--yes`, `-y` | Move without asking for confirmation. |
| `--verbose`, `-v` | Show which rule applied to each file. |
| `--lowercase`, `-l` | Keep folders named after Magika groups lowercase (`video/` instead of `Video/`). |
| `--version`, `-V` | Show the version. |
| `--help`, `-h` | Show the help. |
| `--init-config` | Create a commented example config at the default location (never overwrites an existing one). |
| `--install-completion` | Enable Tab completion of the options in your shell (once is enough). |

Only files directly inside the folder are processed. Existing subfolders are left untouched, so the tool can safely be run again.

| Exit code | Meaning |
| :-: | :--- |
| `0` | Everything went fine, or there was nothing to organize. |
| `1` | At least one file could not be processed, or the confirmation was declined. |
| `2` | Invalid arguments or configuration. |

### Configuration

Without `--config`, mimedy reads your personal configuration file, if it exists:

| System | Location |
|---|---|
| Linux, macOS | `~/.config/mimedy/config.yaml` (or `$XDG_CONFIG_HOME/mimedy/config.yaml`) |
| Windows | `%APPDATA%\mimedy\config.yaml` |

If it doesn't exist, the defaults are used. A file passed with `--config`, however, must exist. `mimedy --help` shows the exact location on your machine.

To get started, create a commented example config, then adapt it:

```bash
mimedy --init-config
# Created config file: /Users/me/.config/mimedy/config.yaml
```

```yaml
hidden: "Hidden"            # files starting with '.'

large_files:
  threshold_mb: 500         # decimal MB, like Finder or Explorer
  target_dir: "Large"

extensions:                 # exact extension match
  .blend: "Blender"
  .csv: "Data"

mimetypes:                  # MIME type detected by Magika
  application/pdf: "PDF"
  image/jpeg: "Photos"
```

Every key is optional: missing ones fall back to their default value. Destinations may include subfolders (`"Code/Python"`). See [`config.example.yaml`](src/mimedy/config.example.yaml), the file copied by `--init-config`, for a complete, commented example.

### How is a file classified?

Rules are evaluated in this order; **the first match wins**:

| # | Rule | Example |
|:-:|:---|:---|
| 1 | Hidden file | `.env` → `Hidden/` |
| 2 | Large file | `movie.mkv` (2 GB) → `Large/` |
| 3 | Extension | `scene.blend` → `Blender/` |
| 4 | MIME type (Magika) | `invoice` *(PDF with no extension)* → `PDF/` |
| 5 | Magika group | `script.py` → `Code/` |

Rules 1 to 3 don't read file contents, so they are instant. Magika only runs when they aren't enough.

### Project structure

```text
mimedy/
├── pyproject.toml
├── src/mimedy/
│   ├── main.py              # CLI entry point (Typer)
│   ├── config.py            # Configuration loading and validation
│   ├── config.example.yaml  # Commented example configuration
│   ├── organizer.py         # Classification rules, planning and moves
│   └── errors.py            # Project exceptions
└── tests/                   # pytest tests (configuration, rules, plan, CLI)
```

### Development

Code is checked by [Ruff](https://docs.astral.sh/ruff/) (linting and formatting) on every commit, and tested with [pytest](https://docs.pytest.org/). Continuous integration runs both on every push, on Python 3.10 to 3.13.

```bash
git clone https://github.com/ochapeau/mimedy.git
cd mimedy
uv sync                     # create the development environment
uv run pre-commit install   # automatic checks on every commit
uv run pytest               # run the tests
uv run mimedy --help        # run the development version
```

### Roadmap

- [x] Typed, validated configuration
- [x] Global configuration in `~/.config/mimedy/`
- [x] Automated tests and continuous integration
- [x] Publish on PyPI (`uv tool install mimedy`)
- [ ] Ignore system files (`.DS_Store`, `.localized`, `Thumbs.db`, `desktop.ini`…), with an option to organize them anyway
- [ ] File patterns to ignore (downloads in progress: `*.part`, `*.crdownload`…)
- [ ] Undo the last run (`--undo`)
- [ ] Optional terminal interface (TUI)

### License

Released under the MIT License. See [LICENSE](LICENSE).
