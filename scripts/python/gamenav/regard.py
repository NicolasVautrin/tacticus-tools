"""L1 bis -- LES PIXELS. Capturer la fenetre du jeu, la mesurer, la redimensionner.

DEUX CANAUX, DEUX USAGES -- ne pas les confondre coute cher
------------------------------------------------------------
`vue` rend des IDENTITES (chemins d'objets Unity) : c'est ce avec quoi on AGIT, et ca tient
en quelques dizaines de lignes de texte. `regard` rend des PIXELS : c'est ce avec quoi on
COMPREND, et ca coute ~(l x h)/750 tokens a lire. Passer par l'image pour cliquer serait a
la fois plus cher et moins precis.

LES QUATRE RATES DE LA MISE AU POINT, tous silencieux, tous corriges ici
------------------------------------------------------------------------
1. DEUX PROCESS s'appellent << tacticus >>. Le premier rendu est le LAUNCHER (minimise,
   160x28). On discrimine par le CHEMIN (`...\\tacticus\\games\\<hash>\\Tacticus.exe`), jamais
   par le nom -- et surtout jamais par << l'image n'est pas noire >>, qui etait vert dessus.
2. `PrintWindow` ne voit pas la swap chain d'Unity : il rend un fragment OBSOLETE, avec
   464/576 pixels non noirs. Non noir n'est pas bon. On capture donc l'ECRAN.
3. Capturer l'ecran exige des coordonnees PHYSIQUES. `SetProcessDPIAware` rend le process
   conscient du DPI *systeme*, c'est-a-dire du moniteur PRIMAIRE : sur un bureau etendu dont
   l'autre ecran est a 250 %, on preleve 1549x925 dans une fenetre qui en fait 3872x2312 --
   soit son coin superieur gauche, lu a tort comme << l'UI deborde >>. La bonne primitive est
   `SetThreadDpiAwarenessContext(-4)` (per-monitor v2).
4. Capturer un RECTANGLE ne garantit pas qu'on capture LA FENETRE : ce qui la recouvre entre
   dans l'image. `WindowFromPoint` au centre le VERIFIE. Sans ce cran, deux captures ont
   ramasse les applications de l'utilisateur.

⚠ UNE CAPTURE UNIQUE NE DIT PAS SI CE QU'ELLE MONTRE EST UN ETAT OU UNE ANIMATION. Mesure :
un bandeau defilant a d'abord ete lu comme un canvas casse. `bouge()` tranche en 2,5 s, en
ventilant le delta par bande verticale -- meme discipline que le clic : l'instantane ne
prouve rien, le delta si.
"""
from __future__ import annotations

import ctypes
import json
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
SORTIES = RACINE / "logs"
MEMOIRE_RECT = SORTIES / "gamenav-fenetre-origine.json"
#: Au-dela, l'image est reduite a la lecture ; en-deca elle est lue en 1:1.
SEUIL_LISIBLE = 1568

_u32 = ctypes.windll.user32
_PER_MONITOR_V2 = ctypes.c_void_p(-4)


class _PT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _dpi_par_moniteur() -> None:
    """A appeler AVANT toute lecture de geometrie. Cf. rate n.3 de l'en-tete."""
    try:
        _u32.SetThreadDpiAwarenessContext(_PER_MONITOR_V2)
    except Exception:                                                # noqa: BLE001
        pass


@dataclass
class Fenetre:
    hwnd: int
    x: int
    y: int
    l: int
    h: int

    @property
    def rect(self) -> tuple:
        return (self.x, self.y, self.x + self.l, self.y + self.h)

    @property
    def lisible(self) -> bool:
        return max(self.l, self.h) <= SEUIL_LISIBLE


def fenetre_du_jeu() -> Fenetre | None:
    """La fenetre du JEU (pas celle du launcher), en pixels physiques. None = PAS MESURE."""
    import subprocess
    _dpi_par_moniteur()
    ps = ("Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and "
          "$_.Path -like '*\\tacticus\\games\\*\\Tacticus.exe' } | "
          "Select-Object -First 1 -ExpandProperty MainWindowHandle")
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30)
        hwnd = int((out.stdout or "").strip())
    except Exception:                                                # noqa: BLE001
        return None
    if not hwnd:
        return None
    r = wintypes.RECT()
    if not _u32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r)):
        return None
    return Fenetre(hwnd, r.left, r.top, r.right - r.left, r.bottom - r.top)


def occupe_par_le_jeu(f: Fenetre) -> bool:
    """Le centre du rectangle appartient-il bien a la fenetre du jeu ? Cf. rate n.4."""
    _dpi_par_moniteur()
    p = _PT(f.x + f.l // 2, f.y + f.h // 2)
    sous = _u32.WindowFromPoint(p)
    if not sous:
        return False
    racine = _u32.GetAncestor(wintypes.HWND(sous), 2)   # GA_ROOT
    return int(racine or sous) == f.hwnd


def capturer(sortie: Path | str | None = None, premier_plan: bool = True):
    """Rend `(chemin, Fenetre)` ou `(None, motif)`. Ne livre JAMAIS une image non situee."""
    from PIL import ImageGrab

    f = fenetre_du_jeu()
    if f is None:
        return None, "fenetre du jeu NON MESUREE (le launcher ne compte pas)"
    if premier_plan:
        _u32.SetForegroundWindow(wintypes.HWND(f.hwnd))
        time.sleep(0.9)
        f = fenetre_du_jeu() or f
    if not occupe_par_le_jeu(f):
        return None, ("le centre du rectangle n'appartient pas au jeu -- une autre fenetre "
                      "le recouvre ; capture ABANDONNEE plutot que livrer les pixels du voisin")
    img = ImageGrab.grab(bbox=f.rect, all_screens=True)
    sortie = Path(sortie) if sortie else SORTIES / "gamenav-capture.png"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    img.save(sortie)
    return sortie, f


def bouge(attente_s: float = 2.5, bandes: int = 16) -> list[tuple] | None:
    """Ce qui CHANGE entre deux captures, par bande verticale. Rend [(x0, x1, pct), ...].

    Trancher << etat >> contre << animation >> demande deux images ; une seule n'en dit rien.
    """
    from PIL import ImageChops, ImageGrab

    f = fenetre_du_jeu()
    if f is None or not occupe_par_le_jeu(f):
        return None
    a = ImageGrab.grab(bbox=f.rect, all_screens=True).convert("RGB")
    time.sleep(attente_s)
    b = ImageGrab.grab(bbox=f.rect, all_screens=True).convert("RGB")
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 12 else 0)
    out = []
    for k in range(bandes):
        x0, x1 = f.l * k // bandes, f.l * (k + 1) // bandes
        bande = diff.crop((x0, 0, x1, f.h))
        n = sum(bande.point(lambda v: 1 if v else 0).getdata())
        out.append((x0, x1, 100.0 * n / max(1, bande.width * bande.height)))
    return out


def redimensionner(largeur: int, hauteur: int, x: int | None = None,
                   y: int | None = None) -> tuple:
    """Redimensionne et RELIT. `MoveWindow` rend `true` meme quand le systeme annule.

    Le rect d'origine est memorise AVANT le premier deplacement, et jamais reecrit : un
    second appel ne doit pas graver une taille deja modifiee comme etant l'origine.
    """
    f = fenetre_du_jeu()
    if f is None:
        return None, "fenetre du jeu NON MESUREE"
    if not MEMOIRE_RECT.exists():
        MEMOIRE_RECT.parent.mkdir(parents=True, exist_ok=True)
        MEMOIRE_RECT.write_text(json.dumps({"x": f.x, "y": f.y, "l": f.l, "h": f.h}),
                                encoding="utf-8")
    _u32.MoveWindow(wintypes.HWND(f.hwnd), f.x if x is None else x,
                    f.y if y is None else y, largeur, hauteur, True)
    time.sleep(1.4)                     # laisser le systeme re-imposer sa contrainte
    apres = fenetre_du_jeu()
    tenu = bool(apres and apres.l == largeur and apres.h == hauteur)
    return apres, ("TENU" if tenu else "RE-IMPOSE par le systeme ou le jeu")


def restaurer() -> tuple:
    if not MEMOIRE_RECT.exists():
        return None, "aucun rect d'origine memorise"
    o = json.loads(MEMOIRE_RECT.read_text(encoding="utf-8"))
    return redimensionner(o["l"], o["h"], o["x"], o["y"])
