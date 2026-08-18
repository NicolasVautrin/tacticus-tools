"""#419-r1-tr14-r4-r3 -- l'ancrage `casterPosition` du slot 2, RE-MESURE : le blocage ecrit etait FAUX.

La fiche annonce `BLOCAGE: porteur` et demande un debloqueur : « un vecteur ou l'attaque normale
s'execute depuis une tuile != position reelle ». **Ce vecteur EXISTE, et il est deja PORTE.**

## Le vecteur -- `MartialExemplarAbility` (1216, `darkaBossLion`), branche ELSE

Arbre natif LU (`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$
ExecuteBehaviour`), branche `els` du `If(AmountIsGreaterThanZero(<attaquables adjacents>), …)` :

    els = DSLBehaviors$$MoveUnit( Owner@+0x30, ClosestPositionToTarget(Owner, Tiles(<cible tiree>)) )
          op_Addition
          DSLBehaviors$$UseNormalAttackIfAble( Owner@+0x30, <cible tiree>, … )

Le caster BOUGE, puis son ATTAQUE NORMALE part. Or `IdunBattle.Entities.Behaviours.
UseActiveAbilityBehaviour$$Execute` -- le corps de `UseNormalAttackIfAble` -- **RECOPIE** les champs
de l'`AbilityEntities` parente (`entities+0x68..+0x74`, la zone `CasterPosition`) dans les options
qu'il passe au processeur : il ne les RECALCULE pas. L'attaque normale est donc evaluee avec le
`casterPosition` d'AVANT le deplacement, pendant que l'unite frappe depuis la tuile d'APRES.

L'ecart est maximal, et il est ORIENTE : `ClosestPositionToTarget` amene le caster AU CONTACT, donc
la position REELLE dit `melee` pendant que l'ancre heritee dit `ranged`
(`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, branche `Normal(3)` :
`!HasFlag(caster, 0x15) && AreEntitiesAdjacent(casterPosition, target)`).

## Le blocage REEL : `etage`, pas `porteur`

Le mirror `Entities` du DSL (`engine/dsl/base.py`) porte `caster`, `owner`, `actor`,
`active_target`, `subject` -- mais **AUCUN champ `caster_position` / `caster_tiles`**, alors que la
carte des selecteurs caches du `DSLFactory` en compte deux (`+0x168 CasterTile`, `+0x170
CasterTiles`) et que le commentaire du mirror les CITE sans les porter. Tant que ce champ n'existe
pas, aucun consommateur du slot 2 ne peut recevoir l'ancre : ils lisent tous la position REELLE.

Point d'ancrage POSE par cette tranche : `engine/runner/battle_query_state.is_melee_attack` accepte
deja `caster_position=` (defaut `None` -> position reelle, degradation NOMMEE). Il ne manque que la
SOURCE.

## #10024 -- L'AUTRE ecart du meme predicat, trouve en le relisant : MAIN TILE vs EMPREINTE

Signature native LUE (`data/symbols/<build>/frida/methods.tsv`) :

    BattleQuery.IsMeleeAttack(ability:Nullable<AbilityOrEffect>, caster:IEntity,
                              casterPosition:**IdunBattle.Core.UnitPosition**, target:IEntity)

`UnitPosition` est une EMPREINTE (liste de tuiles), et le corps appelle la surcharge
`BattleQuery.AreEntitiesAdjacent(tiles:IList<IEntity>, unit:IEntity)` -- donc **empreinte du caster
x empreinte de la cible**. Le port (`engine/services/battle_query.is_melee_attack`) prend deux
TUPLES `(col, row)` et delegue a `engine.battle_query.are_entities_adjacent`, qui compare deux MAIN
TILES. Le foyer d'empreinte EXISTE pourtant dans le meme module
(`engine/services/battle_query.are_entities_adjacent(feet_a, feet_b, board)`, qui documente
explicitement « elle compare les EMPREINTES COMPLETES, pas les main tiles ») -- il n'est simplement
pas celui que ce predicat emprunte. Ecart exercable des qu'une des deux unites est multi-tuiles.

ASCII only.
"""
from __future__ import annotations

import ast
import pathlib
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ENGINE = PYDIR / "engine"


def _src(rel: str) -> str:
    return (ENGINE / rel).read_text(encoding="utf-8")


def etage1_vecteur() -> int:
    """Le vecteur `MoveUnit` -> `UseNormalAttackIfAble` est-il TOUJOURS dans l'arbre porte ?"""
    print("ETAGE 1 -- le DEBLOQUEUR existe-t-il dans le port ?")
    src = _src("runner/abilities/darkangels.py")
    tree = ast.parse(src)
    trouve = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,)) and "martial_exemplar" in node.name:
            noms = {getattr(c.func, "id", None) or getattr(c.func, "attr", None)
                    for c in ast.walk(node) if isinstance(c, ast.Call)}
            if {"MoveUnit", "UseNormalAttackIfAble"} <= noms:
                trouve = True
                print("  %s : MoveUnit ET UseNormalAttackIfAble dans le MEME arbre -> VECTEUR"
                      % node.name)
    if not trouve:
        print("  ROUGE : plus aucun arbre porte n'enchaine MoveUnit puis UseNormalAttackIfAble --")
        print("          le debloqueur de #419-r1-tr14-r4-r3 a disparu, RELIRE la fiche")
        return 1
    print("  => `BLOCAGE: porteur` est FAUX : le vecteur est porte et son porteur")
    print("     (`darkaBossLion`, GuildBoss) se monte par --explicit-stats.")
    return 0


def etage2_etage_manquant() -> int:
    """Le mirror `Entities` du DSL porte-t-il l'ancre ? (c'est le blocage REEL)"""
    print()
    print("ETAGE 2 -- le mirror `Entities` du DSL porte-t-il `caster_position` ?")
    src = _src("dsl/base.py")
    tree = ast.parse(src)
    champs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for st in node.body:
                if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                    champs.add(st.target.id)
    ancres = {c for c in champs if "caster_position" in c or "caster_tile" in c}
    print("  champs d'ancre trouves : %s" % (sorted(ancres) if ancres else "(AUCUN)"))
    if ancres:
        print("  => l'etage est POSE : #419-r1-tr14-r4-r3 devient portable, relire la fiche")
        return 0
    print("  => BLOCAGE REEL = `etage` (le champ n'existe pas), PAS `porteur`.")
    print("     Point d'ancrage deja pose cote runner : `battle_query_state.is_melee_attack`")
    print("     accepte `caster_position=` -- il ne manque que la SOURCE.")
    return 0


def etage3_empreinte() -> int:
    """#10024 : le predicat compare-t-il des MAIN TILES la ou le natif compare des EMPREINTES ?"""
    print()
    print("ETAGE 3 (#10024) -- MAIN TILE vs EMPREINTE dans `services/battle_query.is_melee_attack`")
    src = _src("services/battle_query.py")
    tree = ast.parse(src)
    appelees = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "is_melee_attack":
            for c in ast.walk(node):
                if isinstance(c, ast.Call):
                    f = c.func
                    if isinstance(f, ast.Attribute):
                        base = getattr(f.value, "id", "")
                        appelees.add("%s.%s" % (base, f.attr))
                    elif isinstance(f, ast.Name):
                        appelees.add(f.id)
    print("  appels de `is_melee_attack` : %s" % sorted(appelees))
    par_main_tile = "_bq.are_entities_adjacent" in appelees
    par_empreinte = "are_entities_adjacent" in appelees      # le foyer LOCAL, celui des pieds
    print("  voie MAIN TILE (`engine.battle_query`)  : %s" % par_main_tile)
    print("  voie EMPREINTE (foyer local, feet)      : %s" % par_empreinte)
    if par_main_tile and not par_empreinte:
        print("  CONSTAT #10024 OUVERT : le natif passe un `IdunBattle.Core.UnitPosition`")
        print("  (empreinte) a `AreEntitiesAdjacent(IList<IEntity>, IEntity)` ; le port compare")
        print("  deux main tiles. Ecart exercable des qu'une unite est multi-tuiles.")
        return 0
    print("  CONSTAT : la voie a change -- relire #10024 avant de le citer.")
    return 0


def main() -> int:
    rc = etage1_vecteur()
    rc |= etage2_etage_manquant()
    rc |= etage3_empreinte()
    print()
    print("rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
