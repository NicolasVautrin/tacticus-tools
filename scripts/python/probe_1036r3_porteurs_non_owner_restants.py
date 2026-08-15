"""probe #1036-r3 -- POURQUOI les DERNIERS corps de `TriggeredAbilityNonOwnerPlaybook<T>` ne sont
pas portes. La reponse mesuree n'est PAS celle qu'annoncaient les trois fiches.

Ce que les fiches disaient (toutes trois RE-MESUREES FAUSSES ici) :

  * `#433-r4-r3-r1-r1` : << 11 faces MOVE derivees DIRECTES restent non portees >>. Il en reste
    QUATRE : sept ont ete portees depuis (#477-r33 : 1457/1461/1495 ; #477-r35 : 1469/1526/1531 ;
    #477-r37 : 1064).
  * `#433-r4-r3-r1-r2` : << 3 faces ATTACK + 1 face REPAIR jamais portees ; le port n'a donc pas de
    foyer pour eux : c'est un cablage a creer >>. Le cablage EXISTE : les TROIS dispatchers sont
    portes (`evaluate` / `evaluate_attack_in_steps` / `evaluate_repair_in_steps`) et les TROIS
    registres aussi (`non_owner.py`, `non_owner_attack.py`, `non_owner_repair.py`, #271-r4/#271-r7).
    Il reste UN corps ATTACK, `ShieldOfFaith`.
  * `#1036-r3` / le bloc de commentaire du registre : << gates sur la RARETE, et AUCUN canal
    `rarity` n'existe cote port ; le verrou est un CAPTEUR MANQUANT >>. Le canal EXISTE
    (`UnitContext.rarity`, #999-r3 / capteur #1039) et il est ATTEIGNABLE depuis le `tile_leaf_ctx`
    de la face MOVE, qui publie `ctx["scene"]` (etape 3 ci-dessous).

LE VRAI BLOCAGE, ET IL EST COMMUN AUX QUATRE CORPS QUI RESTENT
---------------------------------------------------------------
Leur PORTEUR est une **MACHINE OF WAR** (voie d'attribution `mythicAbilities`), et l'univers de
porteurs des dispatchers portes est bati sur des entites POSITIONNEES :

  * face MOVE   -- `TriggeredAbilitiesNonOwnerUtility.evaluate` itere `ctx["friend_units"]` +
                   `ctx["enemy_units"]`, que les TROIS `*_leaf_ctx` construisent en exigeant une
                   position (`PositionComponent` cote runner, `pos.col is not None` cote Scene) ;
  * faces ATTACK/REPAIR -- elles iterent `Scene.units`, qui est `decisionView.units`, et le natif
                   expose les MoW dans un canal SEPARE `.mows` (cf. `Scene.machine_ids`).

Or une MoW n'a AUCUNE tuile (`AddMachineOperation$$Execute` ne lui donne pas de
`PositionComponent` ; le port non plus, cf. `snapshot._load_machines`). Le natif, lui, itere
`abilityAndEffectCache.<slot 5>()` -- TOUTES les `TriggeredAbility` de la bataille, MoW comprises.
La paire `(playbook, owner)` n'est donc JAMAIS yieldee cote port : inscrire ces classes au registre
ecrirait du code que le dispatcher n'itere jamais -- le patron #419 que ce depot refuse.

⚠ ET LES CORPS NE LISENT PAS LA POSITION DU PORTEUR -- c'est ce qui rend le diagnostic non
trivial. `MastersOfManoeuvre` ne lit meme PAS `owner` (sa methode-usine ne l'ecrit pas), et
`Cabal`/`Wisdom` ne s'en servent que pour un test d'IDENTITE (`u == owner`) a l'interieur de
`GetAdjacentFriends(tile, case.unit)`. Ce n'est donc pas leur corps qui exige une position : c'est
l'ETAGE au-dessus. Le foyer a reparer est `engine/utilities/tile.py`, pas `engine/playbook/*`.

Le CINQUIEME corps, `SabreOfSacrifice` (1478), est le seul dont le porteur est une unite NORMALE
(`astraDreir`, voie RELIQUE equipable) : son blocage est different et il est nomme a l'etape 4.

Usage :

    cd scripts/python
    python probe_1036r3_porteurs_non_owner_restants.py

Sortie ASCII uniquement. 100 % OFFLINE : aucune session Frida, aucun runner.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------------------------
# ETAGE 0 -- la VENTILATION par FACE, re-derivee de l'entree VERSIONNEE, jamais recopiee
# ---------------------------------------------------------------------------------------------
def _build_courant() -> str:
    with open(os.path.join(RACINE, "data", "symbols", "CURRENT"), encoding="utf-8") as fh:
        return fh.read().strip()


def lire_slot4_tsv() -> list[dict]:
    """`data/symbols/<build>/metadata/non_owner_slot4.tsv` -- les 28 concrets, leur PARENT, leur
    FACE et leur `<slot 4>`. C'est l'entree que #477-r37 a versionnee, donc la seule source qui
    n'exige ni le jeu installe ni ghidra."""
    p = os.path.join(RACINE, "data", "symbols", _build_courant(), "metadata", "non_owner_slot4.tsv")
    out = []
    with open(p, encoding="utf-8") as fh:
        for ligne in fh:
            if not ligne.strip() or ligne.startswith("#"):
                continue
            ch = ligne.rstrip("\n").split("\t")
            out.append({"classe": ch[0], "parent": ch[1], "face": ch[2],
                        "declare": ch[3], "valeur": ch[4]})
    return out


def classes_portees() -> dict[str, set]:
    """Les noms de classe REELLEMENT au registre, par face. Derive des trois registres, jamais
    ecrit : c'est ce qui fait qu'un port livre demain ferme automatiquement une ligne ici."""
    from engine.playbook import non_owner as NO
    from engine.playbook import non_owner_attack as NOA
    from engine.playbook import non_owner_repair as NOR
    return {"MOVE": {type(pb).__name__ for pb in NO.NON_OWNER_MOVE_PLAYBOOKS.values()},
            "ATTACK": {type(pb).__name__ for pb in NOA.NON_OWNER_ATTACK_PLAYBOOKS.values()},
            "REPAIR": {type(pb).__name__ for pb in NOR.NON_OWNER_REPAIR_PLAYBOOKS.values()}}


#: Les classes PORTEES mais VOLONTAIREMENT hors registre, avec la raison MESUREE. Une classe qui
#: n'est ni au registre ni ici est un vrai trou -- c'est le discriminant de l'etape 0.
PORTEES_HORS_REGISTRE = {
    # 1522 : zero porteur sur ce build (deux sources : `unit_map find --ability` et un balayage
    # textuel du gameconfig). L'inscrire serait le patron #419.
    "RedemptionOfTheRisenNonOwnerPlaybook": "0 porteur (patron #419), RE faite et juste",
}


def etape0():
    tsv = lire_slot4_tsv()
    portees = classes_portees()
    par_face = {}
    for r in tsv:
        par_face.setdefault(r["face"], []).append(r["classe"])
    print("ETAPE 0 -- ventilation des %d concrets (source : metadata/non_owner_slot4.tsv, build %s)"
          % (len(tsv), _build_courant()))
    restantes = {}
    for face in ("MOVE", "ATTACK", "REPAIR"):
        toutes = set(par_face.get(face, ()))
        vues = portees[face] | (set(PORTEES_HORS_REGISTRE) & toutes)
        manque = sorted(toutes - vues)
        restantes[face] = manque
        print("  %-7s %2d concrets | %2d portes (%d au registre, %d hors registre) | RESTE %d"
              % (face, len(toutes), len(vues), len(portees[face] & toutes),
                 len(set(PORTEES_HORS_REGISTRE) & toutes), len(manque)))
        for c in manque:
            print("      RESTE : %s" % c)
    # Un nom porte qui ne serait dans AUCUNE face du binaire = un port oriente vers du vide.
    connues = {r["classe"] for r in tsv}
    for face, noms in portees.items():
        orphelines = sorted(n for n in noms
                            if n not in connues and n.replace("NonOwnerPlaybook", "Playbook")
                            not in connues)
        if orphelines:
            print("  ⚠ portees SANS entree binaire (%s) : %r" % (face, orphelines))
    return restantes


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- le PORTEUR de chaque corps restant, et sa NATURE (MoW ou unite normale)
# ---------------------------------------------------------------------------------------------
#: `classe native -> nom d'ability` -- le litteral que le `.ctor` passe a sa base, LU au decompile
#: un par un (`<Classe>$$.ctor` -> `..._ctor(this, <litteral>, ...)`), jamais deduit du nom.
CTOR_LITTERAL = {
    "CabalOfSorcerersPlaybook": 0x5d8,             # 1496 CabalOfSorcerers
    "WisdomOfTheAncientsPlaybook": 0x5ab,          # 1451 WisdomOfTheAncients
    "MastersOfManoeuvreNonOwnerPlaybook": 0x5e4,   # 1508 MastersOfManoeuvre
    "SabreOfSacrificeNonOwnerPlaybook": 0x5c6,     # 1478 SabreOfSacrifice
    "ShieldOfFaithNonOwnerPlaybook": 0x5ad,        # 1453 ShieldOfFaith
}

#: La voie d'attribution `mythicAbilities` designe les mythiques de MACHINE OF WAR : elles sont
#: invisibles de toute autre voie (cf. `docs/rl/case-323-unit-map-attribution-voies.md` Sec.2).
VOIE_MOW = "mythic"


def porteurs_par_voie(nom_ability: str) -> dict[str, list[str]]:
    """`{voie: [unitId]}` -- REUTILISE le recenseur de `unit_map.py` (5 voies derivables) plutot
    que de re-lire le gameconfig a la main : un second recenseur divergerait du premier."""
    import unit_map as UM
    out = {}
    for k in UM.kits():
        for v in UM.carrier_voies(k, nom_ability.lower()):
            out.setdefault(v, []).append(k["id"])
    return out


def etape1(restantes: dict):
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    print("\nETAPE 1 -- le PORTEUR de chaque corps restant (voies derivees par `unit_map`)")
    verdicts = {}
    for face in ("MOVE", "ATTACK", "REPAIR"):
        for classe in restantes.get(face, ()):
            aid = CTOR_LITTERAL.get(classe)
            nom = T(aid).name if aid is not None else "?"
            voies = porteurs_par_voie(nom)
            mow = VOIE_MOW in voies
            verdicts[classe] = {"face": face, "ability": nom, "id": aid, "voies": voies,
                                "porteur_mow": mow}
            print("  %-38s %-7s %-22s id=%d" % (classe, face, nom, aid or -1))
            for v, ids in sorted(voies.items()):
                print("      voie %-8s -> %s" % (v, ", ".join(sorted(ids))))
            print("      PORTEUR MACHINE OF WAR : %s" % ("OUI" if mow else "non"))
    return verdicts


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- l'UNIVERS DE PORTEURS des dispatchers portes exclut-il les MoW ?
# ---------------------------------------------------------------------------------------------
POS = [(c, r) for c in range(3) for r in range(3)]


def _voisins(p):
    c, r = p
    return [q for q in POS if q != p and abs(q[0] - c) <= 1 and abs(q[1] - r) <= 1]


class _Board:
    def __init__(self):
        self.by_id = {i: {"col": p[0], "row": p[1], "elevation": 1, "walkable": True}
                      for i, p in enumerate(POS)}

    def coord(self, tid):
        t = self.by_id[tid]
        return (t["col"], t["row"])

    def neighbours_native(self, tid):
        v = set(_voisins(self.coord(tid)))
        return [i for i, t in self.by_id.items() if (t["col"], t["row"]) in v]


class _Entity:
    def __init__(self, comps):
        self._c = {type(c): c for c in comps}

    def get_component(self, cls):
        return self._c.get(cls)


class _State:
    def __init__(self, entities):
        self.entities = entities
        self.board = _Board()
        self.effects = None

    def get_entity(self, uid):
        return self.entities.get(uid)


def etape2():
    """MESURE, pas deduction : on monte un etat qui contient une MACHINE (entite SANS
    `PositionComponent`, exactement ce que `snapshot._load_machines` produit) et on regarde si elle
    entre dans l'univers que le dispatcher MOVE itere."""
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.utilities.tile import runner_tile_leaf_ctx
    print("\nETAPE 2 -- une MACHINE entre-t-elle dans l'univers de porteurs du dispatcher ?")
    ent = {
        1: _Entity([PositionComponent(0, 0), OwnerComponent(1, 3), UnitComponent("astraDreir", True)]),
        2: _Entity([PositionComponent(1, 1), OwnerComponent(1, 3), UnitComponent("ultraTigurius", True)]),
        # LA MACHINE : aucun `PositionComponent`, comme le natif et comme `_load_machines`.
        9: _Entity([OwnerComponent(1, 3), UnitComponent("thousDaemonPrince", True)]),
    }
    ctx = runner_tile_leaf_ctx(_State(ent), 1, None)
    vus = {u["id"] for u in ctx["friend_units"]} | {u["id"] for u in ctx["enemy_units"]}
    print("  runner_tile_leaf_ctx : univers = %r (la MACHINE porte l'id 9)" % sorted(vus))
    print("  la MACHINE y figure : %s" % ("OUI" if 9 in vus else "NON"))
    # Le jumeau Scene : `decisionView.units` ne contient JAMAIS de Machine (canal `.mows` separe).
    import inspect

    from engine.utilities import tile as TL
    src = inspect.getsource(TL.scene_tile_leaf_ctx)
    lit_units = 'getattr(scene, "units"' in src
    print("  scene_tile_leaf_ctx itere `scene.units` : %s  (canal `.mows` SEPARE, cf. Scene)"
          % ("OUI" if lit_units else "non"))
    src_at = inspect.getsource(TL.TriggeredAbilitiesNonOwnerUtility.evaluate_attack_in_steps)
    print("  evaluate_attack_in_steps itere `sc.units` : %s"
          % ("OUI" if "sc.units" in src_at else "non"))
    return 9 in vus


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- les CANAUX que les corps restants demandent : lesquels existent DEJA ?
# ---------------------------------------------------------------------------------------------
def etape3():
    """La fiche accusait la RARETE. On mesure ce que chaque canal vaut AUJOURD'HUI, un par un."""
    import inspect

    from engine.utilities import tile as TL
    print("\nETAPE 3 -- les canaux demandes par les corps restants")
    for nom, fn in (("tile_leaf_ctx", TL.tile_leaf_ctx),
                    ("scene_tile_leaf_ctx", TL.scene_tile_leaf_ctx),
                    ("runner_tile_leaf_ctx", TL.runner_tile_leaf_ctx)):
        src = inspect.getsource(fn)
        print("  %-22s publie `scene` : %-3s | `self_pos` : %-3s | une cle `rarity`/`vis` du "
              "sujet : %s"
              % (nom,
                 "OUI" if '"scene"' in src else "non",
                 "OUI" if '"self_pos"' in src else "non",
                 "OUI" if ('"unit_rarity"' in src or '"unit_vis"' in src) else "non"))
    from engine.entities.unit_context import UnitContext
    print("  UnitContext porte le champ `rarity` : %s  (canal #1039, consomme #999-r3)"
          % ("OUI" if "rarity" in getattr(UnitContext, "__dataclass_fields__", {}) else "non"))
    print("  => la RARETE est ATTEIGNABLE par `ctx['scene'].ctx(uid).rarity` sur DEUX des trois")
    print("     jumeaux ; elle n'est donc PAS le blocage. Le `visualId` du MOVER, lui, n'est")
    print("     publie par AUCUN des trois (il ne l'est qu'a travers `scene.vis_by_id`).")


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- le cas a part : `SabreOfSacrifice`, seul porteur NON-MoW des cinq
# ---------------------------------------------------------------------------------------------
def etape4():
    print("\nETAPE 4 -- `SabreOfSacrifice` (1478) : porteur NORMAL, blocage DIFFERENT")
    import catalog_inject as CI
    import gameconfig as GC
    print("  porteurs relique (`catalog_inject.relic_carriers`) : %r"
          % (CI.relic_carriers("SabreOfSacrifice"),))
    cst = (GC.ability("SabreOfSacrifice") or {}).get("constants") or {}
    print("  constants : %r" % (cst,))
    print("  gate natif : `IsAffectedSummon(u)` = `AreEqual(Parent(u), Owner) &"
          " IsUnitWithVisualId(u, GetStringConstant(unitId))`")
    print("  -> ARBRE DSL (#149), evalue par vtable +0x188 sur une struct de contexte de 0x128")
    print("     octets (owner a +0x18). Deux manques MESURES, aucun n'est la rarete :")
    print("     (a) le `visualId` du MOVER n'est publie par aucun `*_leaf_ctx` (etape 3) ;")
    print("     (b) l'evaluateur DSL ne se branche pas sur le dict `tile_leaf_ctx`.")
    print("  ⚠ `UtilityMovementCase$$StaysOnTile`, que la fiche citait comme canal manquant, EST")
    print("     disponible : son corps est `GetMainTile(case.unit) == case.Position.MainTile`,")
    print("     c'est-a-dire `tile == ctx['self_pos']`. Cette moitie de la fiche est PERIMEE.")


def main() -> int:
    restantes = etape0()
    verdicts = etape1(restantes)
    mow_dans_univers = etape2()
    etape3()
    etape4()
    print("\n--- SYNTHESE ---")
    bloques_mow = sorted(c for c, v in verdicts.items() if v["porteur_mow"])
    print("corps restants a porteur MACHINE OF WAR : %d -> %r" % (len(bloques_mow), bloques_mow))
    print("la MoW entre dans l'univers de porteurs du dispatcher : %s"
          % ("OUI" if mow_dans_univers else "NON"))
    if bloques_mow and not mow_dans_univers:
        print("VERDICT: BLOCAGE `etage` CONFIRME -- foyer `engine/utilities/tile.py`")
        print("         (univers de porteurs des trois dispatchers), PAS `engine/playbook/*`.")
    else:
        print("VERDICT: le blocage a CHANGE -- relire ce probe et les fiches qu'il porte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
