# mimedy

**Range un dossier en désordre selon le vrai type de chaque fichier, pas selon son extension.**
**Tidies up a messy folder by each file's real type, not by its extension.**

[Français](#français) · [English](#english)

---

<a id="français"></a>

## 🇫🇷 Français

### Pourquoi ?

Un dossier `Téléchargements` finit toujours par ressembler à ça : des PDF, des captures d'écran, des archives, un `.json` exporté un jour, un fichier sans extension dont personne ne se souvient…

La plupart des outils de rangement se fient à l'extension. Or une extension peut mentir, manquer ou être fausse. **mimedy** utilise [Magika](https://github.com/google/magika), le modèle de deep learning de Google qui identifie un fichier **à partir de son contenu**, pour décider où il doit aller.

```text
$ mimedy ~/Downloads --config config.example.yaml
[INFO] Loaded config from config.example.yaml
[INFO] Organizing /Users/me/Downloads
[INFO] Moved '02-gates.pdf' → PDF/
[INFO] Moved 'capsule_wardrobe.csv' → Data/
[INFO] Moved 'photo_2025-04-14_16-07-14.jpg' → Photos/
[INFO] Moved 'random.bin' → Unknown/
[INFO] Moved 'systeme_io.pdf' → PDF/systeme_io (1).pdf
[INFO] Moved 'vid.mp4' → Video/
[INFO] Done: 19 files moved into 12 folders
```

### Fonctionnalités

- 🧠 **Détection par le contenu** : Magika reconnaît plus de 200 types de fichiers, même renommés ou sans extension.
- 🪜 **Règles en cascade** : fichiers cachés, fichiers volumineux, extensions, types MIME, puis le groupe Magika en dernier recours.
- 🔍 **Mode `--dry-run`** : affiche ce qui serait déplacé, sans rien toucher.
- 🛡️ **Aucun écrasement** : si `photo.jpg` existe déjà, le nouveau fichier devient `photo (1).jpg`.
- 🐛 **Mode `--verbose`** : indique pour chaque fichier la règle qui a décidé de sa destination.
- ⚙️ **Configuration YAML** simple, entièrement facultative.

### Installation

Prérequis : Python 3.10+ et [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ochapeau/mimedy.git
cd mimedy
uv sync
```

### Utilisation

> 💡 Commencez toujours par un `--dry-run` pour vérifier le résultat avant de déplacer quoi que ce soit.

```bash
# Aperçu, sans rien déplacer
uv run mimedy ~/Downloads --dry-run

# Rangement réel avec une configuration personnalisée
uv run mimedy ~/Downloads --config my-config.yaml

# Comprendre pourquoi un fichier va à tel endroit
uv run mimedy ~/Downloads --dry-run --verbose
```

| Option | Description |
| :--- | :--- |
| `DIRECTORY` | Dossier à ranger *(obligatoire)*. |
| `--config PATH` | Fichier de configuration YAML *(par défaut : `config.yaml` dans le dossier courant)*. |
| `--dry-run` | Affiche les déplacements prévus sans les effectuer. |
| `--verbose`, `-v` | Affiche la règle appliquée à chaque fichier. |
| `--lowercase` | Garde en minuscules les dossiers nommés d'après Magika (`video/` au lieu de `Video/`). |

Seuls les fichiers situés directement dans le dossier sont traités. Les sous-dossiers existants ne sont pas touchés, ce qui permet de relancer l'outil sans risque.

### Configuration

Copiez l'exemple fourni et adaptez-le :

```bash
cp config.example.yaml config.yaml
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

Toutes les clés sont facultatives : celles qui manquent reprennent leur valeur par défaut. Les destinations peuvent contenir des sous-dossiers (`"Code/Python"`). [`config.example.yaml`](config.example.yaml) contient un exemple complet et commenté.

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
├── config.example.yaml   # Configuration d'exemple commentée
├── pyproject.toml
└── src/mimedy/
    ├── main.py           # Point d'entrée de la CLI (Typer)
    ├── organizer.py      # Règles de classement et déplacement des fichiers
    └── utils.py          # Chargement de la configuration et des logs
```

### Développement

Le code est vérifié par [Ruff](https://docs.astral.sh/ruff/) (lint et formatage), lancé automatiquement à chaque commit :

```bash
uv run pre-commit install
uv run ruff check src
```

### Feuille de route

- [ ] Publication sur PyPI (`uv tool install mimedy`)
- [ ] Configuration typée et validée
- [ ] Configuration globale dans `~/.config/mimedy/`
- [ ] Tests automatisés et intégration continue

### Licence

Distribué sous licence MIT. Voir [LICENSE](LICENSE).

---

<a id="english"></a>

## 🇬🇧 English

### Why?

A `Downloads` folder always ends up looking the same: PDFs, screenshots, archives, a `.json` exported at some point, a file with no extension that nobody remembers…

Most organizing tools trust file extensions. But an extension can lie, be missing, or simply be wrong. **mimedy** uses [Magika](https://github.com/google/magika), Google's deep learning model that identifies a file **from its content**, to decide where it belongs.

```text
$ mimedy ~/Downloads --config config.example.yaml
[INFO] Loaded config from config.example.yaml
[INFO] Organizing /Users/me/Downloads
[INFO] Moved '02-gates.pdf' → PDF/
[INFO] Moved 'capsule_wardrobe.csv' → Data/
[INFO] Moved 'photo_2025-04-14_16-07-14.jpg' → Photos/
[INFO] Moved 'random.bin' → Unknown/
[INFO] Moved 'systeme_io.pdf' → PDF/systeme_io (1).pdf
[INFO] Moved 'vid.mp4' → Video/
[INFO] Done: 19 files moved into 12 folders
```

### Features

- 🧠 **Content-based detection**: Magika recognizes over 200 file types, even when renamed or missing an extension.
- 🪜 **Cascading rules**: hidden files, large files, extensions, MIME types, then the Magika group as a fallback.
- 🔍 **`--dry-run` mode**: shows what would be moved, without touching anything.
- 🛡️ **Never overwrites**: if `photo.jpg` already exists, the new file becomes `photo (1).jpg`.
- 🐛 **`--verbose` mode**: shows which rule decided each file's destination.
- ⚙️ **Simple YAML configuration**, entirely optional.

### Installation

Requirements: Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ochapeau/mimedy.git
cd mimedy
uv sync
```

### Usage

> 💡 Always start with `--dry-run` to check the result before anything is moved.

```bash
# Preview, without moving anything
uv run mimedy ~/Downloads --dry-run

# Actually organize, with a custom configuration
uv run mimedy ~/Downloads --config my-config.yaml

# Understand why a file goes where it goes
uv run mimedy ~/Downloads --dry-run --verbose
```

| Option | Description |
| :--- | :--- |
| `DIRECTORY` | Folder to organize *(required)*. |
| `--config PATH` | YAML configuration file *(default: `config.yaml` in the current directory)*. |
| `--dry-run` | Show planned moves without performing them. |
| `--verbose`, `-v` | Show which rule applied to each file. |
| `--lowercase` | Keep folders named after Magika groups lowercase (`video/` instead of `Video/`). |

Only files directly inside the folder are processed. Existing subfolders are left untouched, so the tool can safely be run again.

### Configuration

Copy the provided example and adapt it:

```bash
cp config.example.yaml config.yaml
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

Every key is optional: missing ones fall back to their default value. Destinations may include subfolders (`"Code/Python"`). See [`config.example.yaml`](config.example.yaml) for a complete, commented example.

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
├── config.example.yaml   # Commented example configuration
├── pyproject.toml
└── src/mimedy/
    ├── main.py           # CLI entry point (Typer)
    ├── organizer.py      # Classification rules and file moves
    └── utils.py          # Configuration and logging setup
```

### Development

Code is checked by [Ruff](https://docs.astral.sh/ruff/) (linting and formatting), run automatically on every commit:

```bash
uv run pre-commit install
uv run ruff check src
```

### Roadmap

- [ ] Publish on PyPI (`uv tool install mimedy`)
- [ ] Typed, validated configuration
- [ ] Global configuration in `~/.config/mimedy/`
- [ ] Automated tests and continuous integration

### License

Released under the MIT License. See [LICENSE](LICENSE).
