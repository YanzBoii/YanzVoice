# YanzVoice

Dictée vocale pour Windows. Tu parles, ça se colle tout seul dans
l'application active — Claude, un navigateur, Word, n'importe quoi.

Transcription par **Groq Whisper large-v3-turbo** (gratuit, sans carte
bancaire). Audio encodé en Opus, ce qui divise la charge réseau par ~9 :
pensé pour tenir sur une connexion faible.

## Installation

### Option A — l'application toute prête (recommandé)

1. Va dans **Releases**, télécharge `YanzVoice-windows.zip`
2. Décompresse-le où tu veux (par exemple `C:\Program Files\YanzVoice`
   ou un dossier perso)
3. Lance `YanzVoice.exe`

Rien d'autre à installer : Python, Qt, PortAudio et libsndfile voyagent
dans l'archive.

Pour ajouter les raccourcis Bureau et menu Démarrer :

```
YanzVoice.exe --install
```

### Option B — depuis les sources

```
git clone https://github.com/<toi>/YanzVoice.git
cd YanzVoice
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\pythonw.exe main.py
```

Pour reconstruire l'exécutable : `.venv\Scripts\python.exe build.py`

## Clé API Groq

Gratuite, sans carte bancaire :

1. https://console.groq.com/keys
2. Connecte-toi, clique **Create API Key**
3. Copie la clé (elle commence par `gsk_`)
4. Dans YanzVoice : **…** → colle-la → **Enregistrer**

La clé est stockée dans `%APPDATA%\YanzVoice\config.json`, jamais dans le
dépôt.

## Passer d'un PC à l'autre

```
YanzVoice.exe --export-config          sauvegarde (clé API incluse)
YanzVoice.exe --import-config <fichier>  restaure sur l'autre machine
```

Le fichier exporté **contient ta clé en clair** : garde-le privé, ne le
dépose jamais dans un dépôt ni sur un partage public. La position de la
pilule et le micro choisi ne sont pas transférés, ils sont propres à chaque
machine.

## Utilisation

La pilule fait 264 × 44 px. Pour la changer, `PILL_W` / `PILL_H` dans
[theme.py](yanzvoice/ui/theme.py).

À chaque apparition, la pastille du micro se montre seule puis la pilule se
déroule vers la droite (620 ms). Le réglage d'accessibilité Windows
« Afficher les animations » désactive l'ouverture s'il est coupé.

| Action | Effet |
|---|---|
| `Ctrl + Espace` | Affiche l'overlay (première pression) |
| `Ctrl + Espace` à nouveau | Démarre / arrête la dictée |
| Clic sur l'icône dictaphone | Démarre / arrête la dictée |
| Glisser l'overlay | Le déplace où tu veux — la position est mémorisée |
| Trois points | Réglages |
| Croix | Masque l'overlay (l'app reste dans la barre des tâches) |

Pendant l'enregistrement, la waveform réagit à ta voix. À l'arrêt, la
transcription part chez Groq (~1 seconde) puis le texte est **collé
automatiquement dans la fenêtre où tu étais** — Claude, un navigateur, Word,
n'importe quoi.

L'overlay ne prend jamais le focus clavier : la fenêtre sous-jacente reste
active, donc le collage atterrit toujours au bon endroit.

Pour quitter : clic droit sur l'icône dans la barre des tâches → **Quitter**.

## Connexion faible

Trois mesures, toutes vérifiables via `--diagnose` :

- **Encodage Opus.** 30 s de parole pèsent 107 Ko au lieu de 937 Ko en PCM,
  soit **8,7× moins**. Sur un lien montant à 0,4 Mbit/s, l'envoi passe de
  19 s à 2,2 s. L'encodage coûte 71 ms. Repli automatique en FLAC puis WAV si
  l'encodeur manque.
- **Silence rogné.** Le blanc avant et après la parole n'est pas envoyé, avec
  une marge de 180 ms pour ne pas couper les consonnes.
- **Connexion préchauffée.** DNS + TCP + TLS démarrent dès que tu appuies sur
  enregistrer, pendant que tu parles. La poignée de main mesurée ici prend
  870 à 1030 ms — autant de retiré à l'attente après la dictée.
- **IPv4 épinglé** quand la résolution IPv6 échoue, ce qui évite de bloquer
  sur une route morte à chaque requête.

## Diagnostic

Quand une dictée échoue, l'overlay affiche une étiquette courte et une
notification Windows donne le détail. Tout est aussi écrit dans
`%APPDATA%\YanzVoice\yanzvoice.log` (menu de la barre des tâches →
**Ouvrir le journal**).

Pour tester chaque couche séparément — DNS, TLS, envoi réel à l'API,
microphone :

```
YanzVoice.exe --diagnose
```

Le rapport s'affiche et s'écrit dans `%APPDATA%\YanzVoice\diagnostic.txt`
— pratique quand l'application tourne sans console.

## Réglages

`%APPDATA%\YanzVoice\config.json` :

| Clé | Rôle |
|---|---|
| `groq_api_key` | Ta clé Groq |
| `model` | `whisper-large-v3-turbo` par défaut (le plus rapide) |
| `language` | `fr`, `en`, … ou `auto` |
| `hotkey` | Syntaxe pynput, ex. `<ctrl>+<alt>+d` |
| `auto_paste` | `false` pour seulement copier dans le presse-papiers |
| `input_device` | Micro mémorisé **par son nom** (les index bougent quand un casque Bluetooth se connecte) ; vide = défaut système |
| `overlay_pos` | `[x, y]` de la pilule, réécrit à chaque déplacement |

La variable d'environnement `GROQ_API_KEY` est utilisée en secours si aucune
clé n'est enregistrée.

## Si ça coince

- **« Aucun son »** — le micro sélectionné ne capte rien. Ouvre les réglages,
  choisis explicitement un périphérique et clique sur **Tester le micro** :
  il affiche le niveau mesuré. Ne te fie pas au défaut système, il change tout
  seul quand un casque Bluetooth se connecte (et les profils *Hands-Free* sont
  en 8 kHz).
- **« Connexion coupée »** — l'envoi a échoué sur les trois stratégies réseau.
  Un antivirus qui inspecte le HTTPS, un VPN ou un pare-feu d'entreprise.
  `--diagnose` te dit laquelle des trois passe.
- **Plusieurs pilules à l'écran** — ne devrait plus arriver : une seule
  instance peut tourner, les lancements suivants se contentent d'afficher
  celle qui existe déjà. Si tu en vois encore, ce sont des processus d'avant
  ce garde-fou ; ferme-les avec la commande ci-dessous puis relance.

  ```
  Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*main.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  ```

  Note : une instance saine occupe **deux** `pythonw.exe` — le relais du venv
  et l'interpréteur réel. C'est normal.
- **`Ctrl+Espace` ne répond pas** — une autre application l'a réservé (le
  sélecteur de langue Windows, par exemple). Change `hotkey` dans
  `config.json`.
- **Le texte ne se colle pas** — il est quand même dans le presse-papiers,
  `Ctrl+V` fonctionne. Certaines applications lancées en administrateur
  refusent les frappes simulées ; lance alors YanzVoice en administrateur.
- **Quota atteint (429)** — le palier gratuit de Groq est généreux mais limité
  par heure ; attends quelques minutes.

## Structure

```
main.py                 point d'entrée
yanzvoice/
  app.py                contrôleur : raccourci, états, orchestration
  audio.py              capture micro + niveaux pour la waveform
  transcribe.py         appel Groq Whisper
  paste.py              presse-papiers + Ctrl+V vers la bonne fenêtre
  config.py             réglages persistés
  encode.py             Opus / FLAC / WAV + rognage du silence
  net.py                connexion préchauffée, IPv4 épinglé, reprises
  diagnose.py           auto-test DNS / TLS / API / micro
  logging_setup.py      journal fichier
  single_instance.py    verrou d'instance unique (tube nommé)
  branding.py           icône, identité barre des tâches, raccourcis
  backup.py             export / import des réglages
  paths.py              chemins des ressources (sources ou exécutable)
  ui/
    overlay.py          la fenêtre glassmorphism
    settings.py         panneau de réglages
    icons.py            icônes vectorielles
    theme.py            tokens « Simple » : couleurs, formes, police
    effects.py          fenêtre sans focus, coins arrondis
assets/icons/           yanzvoice.ico + les SVG du logo
build.py                construit l'exécutable autonome + l'archive
```

## Design

L'interface suit `YanzVoice_design_spec_1.md` (« Simple ») : aplats opaques,
gris uniquement, bordures 1 px, aucun flou, aucun dégradé, aucune ombre,
police système. La seule animation est celle des barres d'écoute, rafraîchies
15 fois par seconde et arrêtées dès que l'enregistrement se termine.

| | |
|---|---|
| Fond | `#1A1A1A` |
| Surface | `#262626` |
| Bordure | `#3A3A3A` (erreur : `#6B6B6B`) |
| Texte | `#EDEDED`, atténué `#A0A0A0` |
| Pilule | 320 × 56, rayon 28 |
| Fenêtre | 640 de large, rayon 12 |

L'écoute se reconnaît au bouton inversé (clair sur fond sombre), l'erreur à
la bordure plus claire — aucune couleur n'est employée.

Deux animations seulement : les barres pendant l'écoute (15 images/s) et
l'ouverture (620 ms). Au repos, le minuteur de rafraîchissement est à l'arrêt.

## Installation manuelle

```bash
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\pythonw.exe main.py
```
