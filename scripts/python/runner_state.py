"""Estampille de SESSION FRIDA sur un state-file de runner, et verification TRI-ETAT.

LE PROBLEME (case-377 §4, residu nomme)
---------------------------------------
Le FICHIER est prive -- un `--state-file` vit dans le `logs/` du worktree de son agent, et
son chemin absolu est justement la cle `owner` du harnais. Aucun agent ne lit le fichier
d'un autre. Mais l'ESPACE D'IDENTIFIANTS, lui, est PARTAGE : il n'existe qu'UN registre de
runners, dans le script injecte (`frida/hooks/game/runner-registry.ts`), commun a tous les
appelants RPC quel que soit leur worktree. Mesure de #395 : entre deux builds consecutifs du
MEME agent, `156` puis `158` -- le `157` avait ete consomme par un autre agent.

    let counter = 0;  ...  runnerId: ++counter   // seul producteur, jamais recycle

DANS une session, cette monotonie suffit : piloter un id perime se fait REFUSER
(`runner N not found`). Le trou est INTER-SESSION. Une (re)injection remet `counter` a `0`
alors que les state-files, eux, SURVIVENT sur disque. Le compteur re-parcourt une plage deja
distribuee et l'id que le state-file rend peut desormais designer le runner d'un AUTRE agent
-- qui ne verra ni erreur ni refus, seulement un etat de bataille qui a avance tout seul, et
qui accusera SON port.

CE SONT LES PETITS NUMEROS LE DANGER, et c'est contre-intuitif. Les ids sont distribues en
ordre CROISSANT : un id BAS (2, 5, 12) tenu a travers une fenetre de reinject devient
dangereux en QUELQUES MINUTES -- le nouveau compteur y arrive tout de suite. Un id HAUT (261)
reste refuse longtemps, le temps que la nouvelle session le rattrape. Un test de collision qui
exercerait un id eleve ne montrerait qu'un refus benin et ferait croire ce garde-fou inutile.

LA CONVENTION -- TRI-ETAT, et la sous-division qui rend l'etat « absente » utile
-------------------------------------------------------------------------------
Le remede est d'ESTAMPER le state-file avec l'identite de la session au `build`, et de
comparer au pilotage. Mais « pas d'estampille » n'est PAS « c'est bon » : c'est
« NON VERIFIABLE », et les deux ne doivent jamais rendre la meme chose (meme discipline que
le tri-etat de `host_inputs`, ou `[introuvable]` reste distinct de `[vide]`).

    MATCH            estampille presente et identique          -> PASSE, silencieux
    MISMATCH         estampille presente et differente         -> REFUS FRANC
    UNSTAMPED_STALE  pas d'estampille, MAIS le fichier est
                     ANTERIEUR au demarrage de la session      -> REFUS FRANC
    UNSTAMPED        pas d'estampille, fichier ecrit PENDANT
                     la session courante                       -> AVERTISSEMENT, non bloquant

`UNSTAMPED_STALE` est ce qui rend l'etat « absente » operant AU LIEU d'etre un aveu poli. Au
moment ou cette garde entre en service, AUCUN state-file du disque ne porte d'estampille --
c'est-a-dire que l'etat le plus dangereux (fichier d'avant une fenetre de reinject) est
exactement celui que l'estampille ne sait pas juger. Le mtime le juge quand meme : un
state-file est RE-ECRIT a chaque action (`_save_state`), donc un mtime anterieur au
`startedAt` de la session courante PROUVE qu'aucune commande ne l'a touche depuis
l'injection. L'inference ne vaut que dans ce sens -- un mtime posterieur ne prouve rien, et
reste `UNSTAMPED`.

Pourquoi ne PAS refuser sur `UNSTAMPED` tout court : un agent qui a build avec du code
d'avant, puis rebase en cours de run (pratique courante ici -- elle est meme exigee avant
d'ouvrir une PR), pilote ensuite avec le code d'apres. Son runner est parfaitement valide.
Refuser la ferait tomber pour rien, et un faux refus sur ce chemin -- traverse par TOUS les
tests live du depot -- couterait plus cher que le bug qu'on ferme.

POURQUOI L'IDENTITE N'EST PAS QUE `sessionId`
---------------------------------------------
`nextSessionId` est un etat de module du HOST (`frida/host/sessions.ts`), pas du bundle
injecte : un redemarrage du host le remet a `1`. Deux sessions distinctes peuvent donc porter
le meme `id`, et une estampille reduite a `id` VALIDERAIT un state-file mort. On estampe le
triplet rendu par `/api/admin/status` -- `id`, `pid`, `startedAt` -- et toute divergence sur
l'un des trois refuse. `startedAt` est un ISO a la milliseconde : deux injections ne le
partagent pas.

Sortie ASCII stricte (console Windows cp1252).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "SESSION_KEY",
    "SessionIdentity",
    "Verdict",
    "MATCH", "MISMATCH", "UNSTAMPED", "UNSTAMPED_STALE",
    "current_identity",
    "stamp",
    "verify",
    "enforce",
]

HOST = os.environ.get("TACTICUS_HOST", "http://127.0.0.1:8765")

#: Cle sous laquelle l'estampille vit dans le state-file. Additive : aucun lecteur
#: existant (archive_demo, engine_agreement_stages, oracle...) ne la voit.
SESSION_KEY = "session"

MATCH = "MATCH"
MISMATCH = "MISMATCH"
UNSTAMPED = "UNSTAMPED"
UNSTAMPED_STALE = "UNSTAMPED_STALE"

#: Marge sur la comparaison mtime <-> startedAt. Le FS (FAT/NTFS via SMB) et l'horloge du
#: host ne sont pas au meme tick ; on ne refuse qu'au-dela. Le filet PRINCIPAL reste
#: l'estampille -- cette branche ne juge que les fichiers ecrits AVANT la garde.
STALE_MARGIN_S = 5.0


@dataclass(frozen=True)
class SessionIdentity:
    """Identite d'UNE session Frida. `id` seul ne suffit pas (cf. docstring du module)."""

    id: int
    pid: int | None = None
    started_at: str | None = None

    def as_dict(self) -> dict:
        return {"id": self.id, "pid": self.pid, "startedAt": self.started_at}

    def label(self) -> str:
        return (f"id={self.id} pid={self.pid if self.pid is not None else '?'} "
                f"startedAt={self.started_at or '?'}")

    @classmethod
    def from_dict(cls, d: dict | None) -> "SessionIdentity | None":
        if not isinstance(d, dict):
            return None
        sid = d.get("id")
        if not isinstance(sid, int):
            return None
        pid = d.get("pid")
        return cls(id=sid,
                   pid=pid if isinstance(pid, int) else None,
                   started_at=d.get("startedAt") if isinstance(d.get("startedAt"), str)
                   else None)

    def same_as(self, other: "SessionIdentity") -> bool:
        """Egalite sur les champs COMPARABLES (un `None` de part et d'autre ne tranche pas).

        Un champ absent d'un cote ne peut pas prouver la divergence -- il ne peut pas non
        plus la nier. On ne conclut donc `False` que sur un desaccord EFFECTIF.
        """
        if self.id != other.id:
            return False
        if self.pid is not None and other.pid is not None and self.pid != other.pid:
            return False
        if (self.started_at is not None and other.started_at is not None
                and self.started_at != other.started_at):
            return False
        return True


def _http_json(path: str, timeout: float = 10.0) -> dict:
    try:
        with urllib.request.urlopen(HOST + path, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except (urllib.error.URLError, OSError, ValueError):
        return {}


def current_identity(status: dict | None = None) -> SessionIdentity | None:
    """Identite de la session Frida courante, ou `None` si le host ne la rend pas.

    `status` permet de reutiliser un `/api/admin/status` deja recupere (pas d'appel HTTP
    supplementaire dans le flux nominal).
    """
    st = status if status is not None else _http_json("/api/admin/status")
    return SessionIdentity.from_dict((st or {}).get("session") or {})


def stamp(payload: dict, ident: SessionIdentity | None) -> dict:
    """Pose l'estampille dans `payload` (mute et rend le meme dict).

    `ident is None` -> on N'ECRIT RIEN : une estampille fabriquee a partir d'une identite
    inconnue mentirait a la relecture. Le fichier reste `UNSTAMPED`, ce qui est la verite.
    """
    if ident is not None:
        payload[SESSION_KEY] = ident.as_dict()
    return payload


def _mtime_utc(path: Path | None) -> datetime | None:
    if path is None:
        return None
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    txt = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Verdict:
    """Resultat TRI-ETAT (+ la sous-division `UNSTAMPED_STALE`) d'une verification."""

    state: str
    current: SessionIdentity | None
    stamped: SessionIdentity | None
    path: Path | None
    runner_id: object = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        """Le state-file est-il UTILISABLE ? `UNSTAMPED` l'est -- mais sans preuve."""
        return self.state in (MATCH, UNSTAMPED)

    @property
    def verified(self) -> bool:
        """A-t-on PROUVE l'appartenance ? Seul `MATCH` repond oui."""
        return self.state == MATCH


def verify(payload: dict, ident: SessionIdentity | None,
           path: Path | None = None) -> Verdict:
    """Confronte l'estampille de `payload` a la session `ident`. Ne leve jamais."""
    stamped = SessionIdentity.from_dict(payload.get(SESSION_KEY))
    rid = payload.get("runnerId")

    if ident is None:
        # Session courante illisible : on ne peut RIEN conclure. Ne pas rendre MATCH.
        return Verdict(UNSTAMPED, None, stamped, path, rid,
                       "identite de la session courante ILLISIBLE (/api/admin/status "
                       "muet) -- aucune comparaison n'a eu lieu")

    if stamped is not None:
        if stamped.same_as(ident):
            return Verdict(MATCH, ident, stamped, path, rid)
        return Verdict(MISMATCH, ident, stamped, path, rid,
                       "l'estampille designe une AUTRE session Frida")

    started = _parse_iso(ident.started_at)
    mtime = _mtime_utc(path)
    if started is not None and mtime is not None:
        if (started - mtime).total_seconds() > STALE_MARGIN_S:
            return Verdict(UNSTAMPED_STALE, ident, None, path, rid,
                           f"pas d'estampille, et le fichier n'a plus ete ecrit depuis "
                           f"{mtime.isoformat()} -- ANTERIEUR au demarrage de la session "
                           f"courante ({started.isoformat()})")
        return Verdict(UNSTAMPED, ident, None, path, rid,
                       f"pas d'estampille ; le fichier a ete ecrit pendant la session "
                       f"courante (mtime {mtime.isoformat()})")
    return Verdict(UNSTAMPED, ident, None, path, rid,
                   "pas d'estampille, et l'anteriorite n'est pas mesurable "
                   "(startedAt ou mtime indisponible)")


# ---- rendu ---------------------------------------------------------------- #

_WHY = (
    "Une (re)injection remet le compteur de runnerId a 0 pendant que les state-files "
    "survivent sur disque. L'id relu peut donc designer le runner d'un AUTRE agent -- qui "
    "ne verrait ni erreur ni refus, seulement une bataille qui avance toute seule.")


def render(v: Verdict, context: str) -> str:
    """Bloc ASCII multi-lignes decrivant le verdict. `context` = l'appelant. Ne decide rien."""
    if v.state == MATCH:
        head = "[session] state-file de la session courante -- OK"
    elif v.state == MISMATCH:
        head = "[error] state-file d'une AUTRE session Frida -- REFUS"
    elif v.state == UNSTAMPED_STALE:
        head = ("[error] state-file SANS estampille et ANTERIEUR a la session courante "
                "-- REFUS")
    else:
        head = ("[warn] state-file SANS estampille -- appartenance NON VERIFIABLE "
                "(ce n'est PAS une validation)")
    body = [f"  appelant   : {context}",
            f"  fichier    : {v.path.as_posix() if v.path else '(inconnu)'}",
            f"  runnerId   : {v.runner_id if v.runner_id is not None else '(aucun)'}"]
    body.append(f"  estampille : session {v.stamped.label()}" if v.stamped is not None
                else "  estampille : ABSENTE")
    body.append(f"  courante   : session "
                f"{v.current.label() if v.current else '(illisible)'}")
    if v.detail:
        body.append(f"  detail     : {v.detail}")
    if v.state in (MISMATCH, UNSTAMPED_STALE):
        body += [
            f"  pourquoi   : {_WHY}",
            "  que faire  : repartir sur un state-file PROPRE --",
            "               python scripts/python/rl_duel.py build "
            "--state-file <nouveau chemin> ...",
            "               NE PAS disposer ce runnerId : il ne vous appartient plus.",
        ]
    elif v.state == UNSTAMPED:
        body += [
            "  que faire  : rien d'obligatoire -- le prochain `build` posera "
            "l'estampille. D'ici la,",
            "               l'appartenance de ce runner a la session courante n'est "
            "PAS prouvee.",
        ]
    return "\n".join([head] + body)


def enforce(v: Verdict, context: str, *, stream=None) -> bool:
    """Imprime le verdict et rend True si l'appelant peut continuer.

    `MATCH` est SILENCIEUX (ce chemin est traverse par tous les tests live du depot : y
    imprimer une ligne a chaque commande noierait les sorties utiles).
    """
    stream = stream if stream is not None else sys.stderr
    if v.state == MATCH:
        return True
    print(render(v, context), file=stream, flush=True)
    return v.ok


if __name__ == "__main__":                        # smoke ASCII
    ident = current_identity()
    print(f"session courante : {ident.label() if ident else '(illisible)'}")
    for arg in sys.argv[1:]:
        p = Path(arg)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"{p.as_posix()} : illisible ({exc})")
            continue
        print(render(verify(data, ident, p), "smoke"))
