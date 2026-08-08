#!/usr/bin/env python3
"""#546 -- LE CLIQUET OFFLINE des capteurs qui attendent LA fenetre de reinject.

    python probe_546_capteurs_fenetre_offline.py

CE QU'IL GARDE, ET POURQUOI IL EST OFFLINE
------------------------------------------
Une tranche de capteurs se livre AVANT sa fenetre : le code part au prochain rebuild, et rien ne
le confronte d'ici la. Entre-temps un rebase, une regeneration de table ou un renommage peut le
vider EN SILENCE -- et la fenetre s'ouvrirait alors sur du code qui publie `null` partout, ce qui
se lit exactement comme « le regime n'existe pas ». Ce probe interdit ce silence : il confronte
les capteurs ECRITS aux tables VERSIONNEES du build courant (`data/symbols/<build>/frida/`), sans
session Frida.

LES QUATRE CAPTEURS DE LA FENETRE
  #287-r10-r1  `NON_GENERIC_RULE_CODES.InFogOfWarBrokenTargetingRule = 1` (rpc-targeting.ts),
               apparie au decodeur Python `targeting_reason.RULE_CLASS_CODES` -- sans lui le RPC
               publie `hex: "0x0"` (« cible VALIDE ») pour un REFUS ;
  #175-r       `tileMeta` publie `door` / `occupantId` / `occupantIsPowerUp` (rpc-board.ts) ;
  #231-r       `effectsAll` enumere les entites-effet HORS de la liste possedee (rpc-snapshot.ts,
               game/effects.ts) ;
  #347-r1      `actorStats[].movement` publie les quatre `Nullable<UnitPositionId>` du
               `MovementComponent` (rpc-snapshot.ts).

LE CRAN QUI COMPTE LE PLUS, ET IL N'EST PAS TEXTUEL. Un capteur resout ses classes et ses methodes
PAR NOM au runtime : un nom faux ne leve rien, il rend `null`. L'etape 5 confronte donc CHAQUE nom
cite par les hooks aux tables du build -- `classes.tsv` pour les classes, `methods.tsv` pour
l'arite ET le nombre de SURCHARGES. C'est ce dernier point qui a deja mordu ici :
`IdunBattle.Entities.UnitExtensions.GetUnit` a **trois** surcharges d'arite 2
(`IEntity` / `FootEntity` / `TileEntity`), donc `findMethodByParamCount` en rendrait une au
hasard. Le probe EXIGE que le hook desambiguise par la classe du parametre.

⚠ UN BALAYAGE QUI NE VISITE RIEN REND ZERO. Chaque etape imprime son TEMOIN et rougit si le temoin
est VIDE : un fichier renomme ou une table illisible doit se voir comme une PANNE, jamais comme un
accord.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ROOT = HERE.parents[1]
HOOKS = ROOT / "frida" / "hooks"
TARGETING = HOOKS / "features" / "ai-step" / "rpc-targeting.ts"
BOARD = HOOKS / "features" / "ai-step" / "rpc-board.ts"
SNAPSHOT = HOOKS / "features" / "ai-step" / "rpc-snapshot.ts"
EFFECTS = HOOKS / "game" / "effects.ts"
DECODEUR = HERE / "targeting_reason.py"


class Panne(RuntimeError):
    """Le probe n'a pas pu MESURER -- distinct d'un desaccord."""


def _lire(p: Path) -> str:
    if not p.exists():
        raise Panne("fichier ABSENT : %s" % p)
    txt = p.read_text(encoding="utf-8")
    if not txt.strip():
        raise Panne("fichier VIDE : %s" % p)
    return txt


_BLOC = re.compile(r"/\*.*?\*/", re.S)
_LIGNE = re.compile(r"(^|\s)//.*$", re.M)


def _code_seul(txt: str) -> str:
    """Le texte PRIVE de ses commentaires.

    ⚠ CE FILTRE EST LOAD-BEARING, et c'est une contre-epreuve qui l'a impose : une premiere
    version cherchait les cles publiees dans le fichier ENTIER, or chacune est aussi CITEE dans
    la docstring du RPC qui la publie. Retirer la ligne de code laissait donc le cliquet VERT --
    il gardait la prose, pas le capteur. Meme vice que le premier jet de
    `test_the_just_summoned_family_stays_out_because_nothing_POSES_it`, qui avait vu un
    `AddEffect(1061)` dans un commentaire disant qu'il n'y en avait pas."""
    return _LIGNE.sub("", _BLOC.sub("", txt))


def _build_courant() -> str:
    """Le build qui FAIT FOI -- foyer unique `symbols_layout.current_build()`."""
    from symbols_layout import current_build
    return current_build()


def _tables(build: str):
    d = ROOT / "data" / "symbols" / build / "frida"
    classes, methodes = set(), []
    cp, mp = d / "classes.tsv", d / "methods.tsv"
    if not cp.exists() or not mp.exists():
        raise Panne("tables du build %s absentes (%s)" % (build, d))
    for ligne in cp.read_text(encoding="utf-8", errors="replace").splitlines():
        if ligne.startswith("#!") or not ligne:
            continue
        classes.add(ligne.split("\t", 1)[0])
    for ligne in mp.read_text(encoding="utf-8", errors="replace").splitlines():
        if ligne.startswith("#!") or not ligne:
            continue
        ch = ligne.split("\t")
        if len(ch) < 6:
            continue
        # rva, nom PLEIN, type declarant, static?, type de retour, parametres
        params = [x for x in ch[5].split(",") if x]
        methodes.append((ch[1], len(params), ch[5]))
    if not classes or not methodes:
        raise Panne("tables du build %s ILLISIBLES (classes=%d methodes=%d)"
                    % (build, len(classes), len(methodes)))
    return classes, methodes


# ------------------------------------------------------------------ etapes


def etape1_brouillard() -> list:
    """#287-r10-r1 -- la ligne du hook ET le decodeur Python portent la MEME classe, MEME code."""
    ko = []
    hook = _lire(TARGETING)
    py = _lire(DECODEUR)
    bloc = re.search(r"NON_GENERIC_RULE_CODES[^{]*\{(.*?)\n\};", hook, re.S)
    if not bloc:
        raise Panne("`NON_GENERIC_RULE_CODES` introuvable dans %s" % TARGETING.name)
    entrees = dict(re.findall(r"(\w+):\s*(0x[0-9a-fA-F]+|\d+)", bloc.group(1)))
    if not entrees:
        raise Panne("`NON_GENERIC_RULE_CODES` VIDE -- temoin nul")
    print("  temoin : %d classe(s) dans le hook -> %s" % (len(entrees), sorted(entrees)))
    from targeting_reason import RULE_CLASS_CODES
    if not RULE_CLASS_CODES:
        raise Panne("`targeting_reason.RULE_CLASS_CODES` VIDE -- temoin nul")
    for cls, brut in entrees.items():
        code = int(brut, 16) if brut.lower().startswith("0x") else int(brut)
        if cls not in RULE_CLASS_CODES:
            ko.append("hook publie `%s` que le decodeur Python IGNORE (il rendrait None)" % cls)
        elif RULE_CLASS_CODES[cls] != code:
            ko.append("`%s` : hook=%d decodeur=%d" % (cls, code, RULE_CLASS_CODES[cls]))
    for cls in RULE_CLASS_CODES:
        if cls not in entrees:
            ko.append("le decodeur Python connait `%s`, le hook NON : le RPC publiera "
                      "`hex: \"0x0\"` -- donc « cible VALIDE » -- pour ce REFUS" % cls)
    if "InFogOfWarBrokenTargetingRule" not in entrees:
        ko.append("la ligne BROUILLARD (#287-r10-r1) a disparu du hook")
    return ko


def etape2_tilemeta() -> list:
    """#175-r -- `tileMeta` publie porte + occupant, et DIT ce qu'il a resolu."""
    hook = _code_seul(_lire(BOARD))
    attendus = ["door", "occupantId", "occupantIsPowerUp", "roomTileType", "isInFog",
                "doorMeasured", "occupantMeasured", "powerUpMeasured",
                "isActivationTileOfClosedDoor"]
    ko = ["`tileMeta` ne publie plus `%s` (#175-r)" % k for k in attendus if k not in hook]
    print("  temoin : %d cle(s) attendue(s), %d presente(s)"
          % (len(attendus), len(attendus) - len(ko)))
    # Le PREDICAT natif, fige : `IsActivationTile` = tuile d'activation d'une porte FERMEE.
    if "isActivationTileOfClosedDoor: isOpen === null ? null : !isOpen" not in hook:
        ko.append("le predicat de `…DoorOpeningUtility$$IsActivationTile` (`!IsOpen`) n'est "
                  "plus ecrit tel quel")
    return ko


def etape3_effectsall() -> list:
    """#231-r -- l'enumeration GLOBALE des entites-effet, et ses trois signatures."""
    eff = _code_seul(_lire(EFFECTS))
    snap = _code_seul(_lire(SNAPSHOT))
    ko = []
    if "export function readAllEffects" not in eff:
        ko.append("`readAllEffects` n'est plus exporte par game/effects.ts (#231-r)")
    if "ctx.rpc.effectsAll" not in snap:
        ko.append("le RPC `effectsAll` n'est plus enregistre (#231-r)")
    champs = ["ownerId", "ownerType", "inOwnerList", "beingRemoved", "initialTurns",
              "hasTurns", "parentEffect", "subEffects"]
    manquants = [c for c in champs if c not in eff]
    ko += ["`OrphanableEffectInfo` ne porte plus `%s` (#231-r)" % c for c in manquants]
    print("  temoin : %d champ(s) discriminant(s), %d present(s)"
          % (len(champs), len(champs) - len(manquants)))
    # Le TROIS-ETATS doit rester LISIBLE : sans `orphanCount`, un `count: 0` ne dit pas de quoi
    # il est le zero.
    for k in ("orphanCount", "removedCount"):
        if k not in snap:
            ko.append("`effectsAll` ne ventile plus `%s` -- un zero redeviendrait muet" % k)
    return ko


#: #347-r1 -- les quatre champs MESURES sur `rnca9r7q6c` (`dumpEntityComponents` sur une unite).
#: Figes ICI parce qu'un mirror regenere redeviendrait vert alors que le SITE, lui, a change :
#: c'est le cran « figer l'ordinal ECRIT AU SITE ».
MOUVEMENT_ATTENDU = {
    "turnStartPosition": ("TurnStartPosition", 0x78),
    "previousPosition": ("PreviousPosition", 0x88),
    "previousPositionThisTurn": ("PreviousPositionThisTurn", 0x98),
    "pendingPosition": ("PendingPosition", 0xa8),
}


def etape4_mouvement() -> list:
    """#347-r1 -- le composant est `MovementComponent`, PAS `UnitComponent`."""
    snap = _code_seul(_lire(SNAPSHOT))
    ko = []
    bloc = re.search(r"MOVEMENT_POS_FIELDS[^=]*=\s*\[(.*?)\n\];", snap, re.S)
    if not bloc:
        raise Panne("`MOVEMENT_POS_FIELDS` introuvable dans %s" % SNAPSHOT.name)
    lus = dict()
    for k, n, f in re.findall(
            r'key:\s*"(\w+)",\s*name:\s*"(\w+)",\s*fallback:\s*(0x[0-9a-fA-F]+)',
            bloc.group(1)):
        lus[k] = (n, int(f, 16))
    if not lus:
        raise Panne("`MOVEMENT_POS_FIELDS` VIDE -- temoin nul")
    print("  temoin : %d champ(s) de position lus dans le hook" % len(lus))
    for k, (nom, off) in MOUVEMENT_ATTENDU.items():
        if k not in lus:
            ko.append("le champ `%s` a disparu du capteur (#347-r1)" % k)
        elif lus[k] != (nom, off):
            ko.append("`%s` : hook=%s attendu=%s" % (k, lus[k], (nom, hex(off))))
    if 'findClassAnywhere(\n    "IdunBattle.Entities.Components", "MovementComponent")' not in snap:
        ko.append("le capteur ne resout plus `MovementComponent` -- `case-347` §8 nomme "
                  "`UnitComponent+0x98`, qui est `PendingHit` sur ce build")
    if "movementLayout" not in snap:
        ko.append("`actorStats` ne publie plus `movementLayout` -- un `movement: null` "
                  "partout redeviendrait indiscernable de « personne n'a bouge »")
    if "ToTileList" not in snap:
        ko.append("le decodage n'invoque plus `UnitPositionIdExtensions$$ToTileList`")
    # --- #347-r3 : ce que la FENETRE du 2026-08-08 a impose -----------------------------------
    # La disposition du `Nullable<T>` etait SUPPOSEE (`off + 8`), et la mesure a montre que la
    # transition `null -> non-null` ne discrimine PAS les deux dispositions possibles : le
    # drapeau « marche » aussi bien quand l'octet lu est l'octet bas du POINTEUR de liste. Le
    # capteur doit donc DERIVER la disposition des metadonnees, et publier de quoi le contredire.
    if "nullableLayoutOf" not in snap:
        ko.append("la disposition du `Nullable<T>` n'est plus DERIVEE des metadonnees "
                  "(`nullableLayoutOf`) -- elle serait de nouveau SUPPOSEE (#347-r3)")
    # FOYER UNIQUE. `nullableLayoutOf` vit dans `internals.ts` (pose par #579-r1 sur le MEME
    # defaut) ; la premiere reparation de ce capteur en avait ecrit une SECONDE copie ici. Une
    # parade en deux exemplaires derive en silence -- c'est le patron que `case-287-r12` a eu a
    # defaire en TROIS exemplaires.
    if "function nullableLayoutOf" in snap:
        ko.append("une COPIE locale de `nullableLayoutOf` est revenue dans rpc-snapshot.ts : "
                  "le foyer unique est `internals.ts` (#579-r1)")
    internals = _code_seul(_lire(HOOKS / "features" / "ai-step" / "internals.ts"))
    if "export function nullableLayoutOf" not in internals:
        ko.append("`internals.ts` n'EXPORTE plus `nullableLayoutOf` -- le capteur de mouvement "
                  "ne peut plus le consommer et une copie va repousser (#347-r3)")
    if "off + 8" in snap:
        ko.append("`off + 8` est REVENU dans le capteur de mouvement : c'est la disposition "
                  "SUPPOSEE que #347-r3 a retiree (`match-state.ts` mesure hasValue EN PREMIER "
                  "sur ce build)")
    for cle in ("nullableLayout", "decode", "raw"):
        if cle not in snap:
            ko.append("`actorStats[].movement` ne publie plus `%s` -- une cause de mutisme "
                      "redeviendrait indiscernable des trois autres (#347-r3)" % cle)
    # Les QUATRE causes doivent rester NOMMEES et DISTINCTES : c'est ce qui a manque a la
    # premiere fenetre (`{tiles: null}` couvrait les quatre).
    for cause in ("layout-not-derived", "hasValue-unreadable", "no-ToTileList",
                  "null-list", "threw"):
        if '"%s"' % cause not in snap:
            ko.append("la cause de mutisme `%s` n'est plus nommee (#347-r3)" % cause)
    return ko


#: Les NOMS que les capteurs resolvent au runtime. Un nom faux ne leve rien : il rend `null`.
CLASSES_CITEES = [
    "IdunBattle.Entities.Components.DoorComponent",
    "IdunBattle.Entities.Components.DoorActivationComponent",
    "IdunBattle.Entities.Components.MovementComponent",
    "IdunBattle.Entities.Components.EffectComponent",
    "IdunBattle.Entities.Components.EffectsOwnedComponent",
    "IdunBattle.Core.UnitPositionIdExtensions",
]
#: (nom PLEIN, arite attendue). L'arite est comparee a la table, pas supposee.
METHODES_CITEES = [
    ("IdunBattle.Core.UnitPositionIdExtensions.ToTileList", 2),
    ("IdunBattle.Entities.UnitExtensions.IsPowerUp", 1),
    ("IdunBattle.Entities.UnitExtensions.GetUnit", 2),
]


def etape5_noms_du_build(build: str) -> list:
    """Les noms CITES par les capteurs existent dans les tables VERSIONNEES du build courant."""
    classes, methodes = _tables(build)
    ko = []
    print("  temoin : %d classe(s) et %d methode(s) dans les tables de %s"
          % (len(classes), len(methodes), build))
    for c in CLASSES_CITEES:
        if c not in classes:
            ko.append("classe CITEE par un capteur, ABSENTE du build %s : %s" % (build, c))
    par_nom = {}
    for nom, arite, _ in methodes:
        par_nom.setdefault(nom, []).append(arite)
    for nom, arite in METHODES_CITEES:
        arites = par_nom.get(nom)
        if not arites:
            ko.append("methode CITEE par un capteur, ABSENTE du build %s : %s" % (build, nom))
        elif arite not in arites:
            ko.append("`%s` : arite %d attendue, le build ne porte que %s"
                      % (nom, arite, sorted(set(arites))))
    # LE CRAN DES SURCHARGES. `GetUnit` en a TROIS d'arite 2 : resoudre par l'arite en rendrait
    # une au hasard, et deux des trois ne prennent pas une tuile.
    n_getunit = sum(1 for a in par_nom.get("IdunBattle.Entities.UnitExtensions.GetUnit", [])
                    if a == 2)
    board = _code_seul(_lire(BOARD))
    if n_getunit > 1 and 'findMethodByParamClasses(unitExtClass, "GetUnit"' not in board:
        ko.append("`GetUnit` a %d surcharges d'arite 2 sur ce build et le hook ne desambiguise "
                  "PAS par la classe du parametre -- il en resoudrait une au hasard" % n_getunit)
    print("  temoin : `GetUnit` porte %d surcharge(s) d'arite 2" % n_getunit)
    if n_getunit == 0:
        raise Panne("aucune surcharge `GetUnit` d'arite 2 -- table suspecte, mesure REFUSEE")
    return ko


def main() -> int:
    etapes = [
        ("1. #287-r10-r1 -- la ligne BROUILLARD, hook <-> decodeur", etape1_brouillard),
        ("2. #175-r      -- `tileMeta` : porte + occupant power-up", etape2_tilemeta),
        ("3. #231-r      -- `effectsAll` : les entites-effet ORPHELINES", etape3_effectsall),
        ("4. #347-r1     -- `actorStats[].movement` : MovementComponent", etape4_mouvement),
    ]
    total = []
    print("=== #546 : cliquet OFFLINE des capteurs qui attendent la fenetre ===")
    try:
        build = _build_courant()
    except Exception as exc:                                          # noqa: BLE001
        print("PANNE : build courant non resolu (%s)" % exc)
        return 2
    print("build courant = %s" % build)
    for titre, fn in etapes:
        print("\n%s" % titre)
        try:
            ko = fn()
        except Panne as exc:
            print("  PANNE : %s" % exc)
            return 2
        for m in ko:
            print("  KO : %s" % m)
        if not ko:
            print("  OK")
        total += ko
    print("\n5. Les NOMS cites existent dans le build courant")
    try:
        ko = etape5_noms_du_build(build)
    except Panne as exc:
        print("  PANNE : %s" % exc)
        return 2
    for m in ko:
        print("  KO : %s" % m)
    if not ko:
        print("  OK")
    total += ko
    print("\n=== VERDICT === %d ecart(s)" % len(total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
