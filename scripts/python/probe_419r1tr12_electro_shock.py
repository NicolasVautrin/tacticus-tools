"""#419-r1 tranche 12 -- MONTAGE NOMME de la face ATTACK d'`ElectroShock` (1303), natif contre port.

`IdunBattle.AI.Playbook.Loki.ElectroShockPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
verse `ElectroShock_TargetHasAdjacentEnemy` (50) SI la CIBLE a au moins un ennemi DU CASTER adjacent
(ring-1 avec porte d'elevation, `ignoreSteppables: false`), et ne yield RIEN sinon. RE complete et
lectures non devinables : `engine/playbook/electro_shock.py` (en-tete).

## DEUX MONTAGES, et c'est le porteur qui les separe

Les 3 porteurs de 1303 sont 2 npc (`admecNpc3Electropriest`, `admecNpc3ElectropriestSurv`) et le
SUMMON `admecSmnElectropriest`.

  `GRAFT` (tranche 12)     GREFFE du passif sur `tauMarksman`, HERO au pool.
  `REAL`  (#419-r1-tr12-r2) le PORTEUR NPC lui-meme, avec ses stats, ses traits et son arme.

Le montage `GRAFT` a ete monte parce que `buildNormalizedBC` REFUSAIT tout npc : sa formule de stats
unique (`IStatsFormula.StatsUsingProgressionIndexFor`, celle des HEROS) leve sur une unite sans table
de progression de heros, et le RPC la range dans `skipped` (« v2 patch: system error »). La greffe est
LEGITIME et c'est LU, pas suppose : le corps du playbook ne consulte du caster QUE son camp
(`OwnerComponent.CurrentPlayerEntityId`, via la surcharge `ref` du slot) -- ni stat, ni trait, ni
arme, ni variable d'ability. Le summon, lui, n'a AUCUN invocateur-unite : le balayage prescrit par
`case-92` §5bis recours 2 rend une seule ability qui le declare,
`EnvFactionSummons:AdeptusMechanicus`, que PERSONNE ne porte -- summon d'ENVIRONNEMENT, donc pas de
voie « spawner son summoner ».

Depuis #419-r1-tr12-r2, `buildNormalizedBC` a un chemin de stats EXPLICITE (`explicitStats`, mirror
de `IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats`) et le npc entre au pool avec SES
propres valeurs. Les deux montages sont donc GARDES tous les deux, et ils ne sont pas redondants :
cf. « ce que chaque montage exerce » plus bas.

## Le BRAS APPARIE -- ce qui rend le terme MESURABLE cote NATIF

Deux runners, IDENTIQUES en tout sauf le passif 1303 :

    bras `graft` : `BC.Units[<hote>].PassiveAbilities` CONTIENT 1303
    bras `base`  : le MEME bloc, MOINS 1303

`terme_natif = natif_graft - natif_base` sur la MEME paire, la MEME tuile et la MEME geometrie.
Sans ce bras, on ne pourrait qu'opposer le natif au port MUTE, ce qui melange le terme et les
residus hors-perimetre du couple (caster, cible). ⚠ Le bras `base` est le bras d'en face MOINS 1303,
surtout PAS « les passifs d'origine de l'hote » : sur `GRAFT`, `replace=True` les a deja retires, et
les remettre ferait differer les deux bras de DEUX abilities (piege mesure par #419-r1-tr9).

## LA TUILE D'ACTION N'EST PAS LA POSITION DU CASTER -- et c'est ce qui sauve le montage MELEE

`pairUtility` prend `col`/`row` : il resout la tuile dans le movable set du caster
(`BattleQuery$$GetMovableTiles`) et construit un `UnitPosition` par `GetUnitPositionAtTile`. Il ne
DEPLACE rien dans l'ECS. Or le playbook lit `GetAdjacentEnemies(case.Target, case.Caster, false)`,
dont l'ancre geometrique est la CIBLE et dont les occupants sont lus par `GetUnit(tile)` sur l'etat
REEL. La position ECS du caster compte donc, sa tuile d'action non -- et le port fait pareil
(`count_adjacent_by_camp` lit `scene.pos`, `attack_tile` est accepte et ignore).

C'est ce qui permet au porteur MELEE de garder les quatre crans intacts : le caster reste GARE loin
de sa cible (donc il n'est pas un voisin), et la paire est evaluee depuis une tuile `A` adjacente a
la cible et atteignable par son mouvement. Sans cette lecture, un caster de melee serait un voisin
AMI permanent de sa cible : `c0` ne serait plus « zero voisin », et les contre-epreuves
`friends` / `any_neighbour` / `no_gate` deviendraient CO-LINEAIRES (elles mordraient exactement les
memes crans) -- l'axe CAMP cesserait d'etre exerce.

## Les QUATRE crans, et ce que chacun est SEUL a trancher

La cible `T` et le caster `C` ne bougent JAMAIS ; on ne deplace que ce qui l'entoure. Le cardinal
est RE-DERIVE des positions live avec l'adjacence NATIVE (`bq.is_adjacent`, porte d'elevation
comprise), jamais suppose.

    `c0`  0 voisin                      -> terme 0    (`Count == 0` -> `yield break`)
    `cF`  1 voisin AMI du caster        -> terme 0    <- CAMP : `Enemies`, pas « voisins »
    `c1`  1 voisin ENNEMI               -> terme 50   <- le terme existe
    `c2`  2 voisins ENNEMIS             -> terme 50   <- PLAT, pas PRODUIT

⚠ `c2` est LE cran de cette tranche. `Boltstorm` (1090), `FireOfAbsolution` (1017) et
`RighteousRepugnance` (1107) comptent tous des voisins de la cible avec le MEME helper `get_Count`
et MULTIPLIENT ; ici le compte ne sert qu'au test `== 0`. Un montage sans deuxieme cran non nul ne
distingue pas les deux modeles, et une recopie par analogie rendrait `100` la ou le natif rend `50`.
Le probe REFUSE si `c1` et `c2` n'ont pas des cardinaux 1 et 2 re-derives.

## Ce que chaque montage exerce, et pourquoi les DEUX restent

`GRAFT` exerce le CORPS du playbook sur un hote neutre : c'est lui qui a etabli que le terme est
plat et ancre sur le camp du caster. `REAL` exerce le MEME corps sur le porteur que le jeu lui
donne -- ses traits (`Mechanical`, `Resilient`), son arme (3 hits `Particle`, MELEE), son
`Movement` 3, ses stats de catalogue -- et il est le SEUL a pouvoir montrer qu'aucun de ces etages
n'entre dans le terme. Un accord sur `GRAFT` seul laisserait ouverte l'hypothese « le terme depend
d'un attribut que `tauMarksman` n'a pas ».

## Contre-epreuves -- critere = DEPLACEMENT par rapport au port NON MUTE

Jamais l'ecart au natif : la paire porte des residus hors-perimetre, donc `abs(port - natif) > EPS`
serait VRAI meme pour un mutant inerte (piege #441/#446).

  `product`       -- `50 x n` au lieu de `50`              -> mord en `c2`
  `any_neighbour` -- compte TOUS les voisins (amis inclus) -> mord en `cF`
  `no_gate`       -- terme 50 inconditionnel               -> mord en `c0` et `cF`
  `friends`       -- compte les AMIS au lieu des ennemis   -> mord en `cF`, `c1`, `c2`

Chaque mutant est joue a TOUS les crans ; la reciproque compte : un mutant qui mordrait partout ne
discriminerait rien.

Usage :
    python scripts/python/probe_419r1tr12_electro_shock.py --state-file <chemin ABSOLU>
        [--state-file-base <chemin ABSOLU>] [--montage graft|real] [--mutants]

ASCII only. Gardes jumelles :
`scripts/python/tests/engine/test_419r1tr12_electro_shock_live.py` (GRAFT) et
`scripts/python/tests/engine/test_419r1tr12r2_electro_shock_reel_live.py` (REAL).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject                                            # noqa: E402
import gameconfig as G                                           # noqa: E402
import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_380_seed_bc_patch_survival as P380                  # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
ABILITY = int(TriggeredAbilityType.ElectroShock)                 # 1303
WEIGHT_KEY = "ElectroShock_TargetHasAdjacentEnemy"
EPS = 1e-4                      # Fix64 natif contre float du port
HP = 40000                      # personne ne doit mourir : `Health` ET `RemainingHealth` (#438)

# Cardinal ENNEMI attendu par cran, re-derive et VERIFIE contre les positions live.
STEPS = ("c0", "cF", "c1", "c2")
EXPECTED_COUNT = {"c0": 0, "cF": 0, "c1": 1, "c2": 2}
MUTANTS = ("product", "any_neighbour", "no_gate", "friends")


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- profils de montage

@dataclasses.dataclass(frozen=True)
class Montage:
    """UN montage nomme. Ce qui varie d'un porteur a l'autre, et RIEN d'autre.

    `host` est l'unitId du CASTER (suffixe `:<level>` compris pour un npc) ; `visual` son
    `VisualId`, la cle par laquelle `--unit-stat` patche le BC normalise. La PORTEE de son arme
    n'est PAS un champ : elle est LUE au gameconfig par `weapon_reach`, parce qu'un porteur reel
    n'a aucune raison d'avoir l'arme de son greffon."""

    key: str
    seed: str
    host: str
    visual: str
    ally: str
    target: str
    foe1: str
    foe2: str
    build_extra: tuple = ()
    board: str = BOARD
    #: Comment le seed BC des deux bras est PRODUIT -- `graft` (le passif est greffe sur un heros
    #: du pool) ou `real` (le porteur est injecte au catalogue avec ses propres passifs). Champ
    #: DISTINCT de `key` : deux profils peuvent partager la meme voie de production.
    bc_kind: str = "real"

    @property
    def mine(self) -> tuple:
        return (self.host, self.ally)

    @property
    def foes(self) -> tuple:
        return (self.target, self.foe1, self.foe2)


GRAFT = Montage(
    key="graft", seed="41303",
    host="tauMarksman",             # HERO au pool, arme distance portee 3 -- greffon, `replace=True`
    visual="tauMarksman",
    ally="necroWarden",             # AMI du caster : le voisin du cran `cF`
    target="astraBullgryn",         # la cible, FIXE dans tous les crans
    foe1="astraCreed", foe2="astraDreir",
    bc_kind="graft",
)

REAL = Montage(
    key="real", seed="41303",
    # Le porteur REEL. Meme kit que le summon `admecSmnElectropriest` (memes passifs, meme arme
    # 3 hits `Particle`, meme `Movement` 3) -- la seule difference etant le trait `Summon` -- et
    # lui a une table `stats[]`, donc `--explicit-stats` peut l'amener au pool. Le suffixe `:33`
    # est le PALIER lu par `idun.shared.UnitNamingConventions$$GetLevelFromUnitId`.
    host="admecNpc3Electropriest:33",
    visual="admecNpc3Electropriest",
    ally="necroWarden",
    target="astraBullgryn",
    foe1="astraCreed", foe2="astraDreir",
    build_extra=("--explicit-stats", "admecNpc3Electropriest:33"),
)

REAL_SURV = dataclasses.replace(
    REAL, key="real_surv",
    # SECOND porteur npc, meme kit (memes passifs, meme arme, meme `Movement`) mais des stats de
    # catalogue d'un tout autre ordre : `Damage` 47656 contre 1765, `FixedArmor` 16248 contre 490,
    # `AbilityVariablesMultiplierPercentage` 180. Les deux lignes sont pourtant « Rank 17 » -- la
    # TABLE discrimine la ou le rank ne discrimine pas. C'est le bras de GENERALISATION : le
    # composite de degat de la paire bouge d'un facteur, le TERME du playbook ne doit pas bouger
    # du tout.
    host="admecNpc3ElectropriestSurv:33",
    # ⚠ MEME `VisualId` que le premier npc : le gameconfig donne `admecNpc3Electropriest` aux DEUX
    # (`Surv` est une variante de progression, pas un autre visuel). Le `VisualId` est la cle de
    # `--unit-stat` ET le discriminant de `_roster` -- d'ou le refus d'ambiguite de ce dernier :
    # amener les deux npc dans la MEME equipe rendrait le montage indeterminable.
    visual="admecNpc3Electropriest",
    build_extra=("--explicit-stats", "admecNpc3ElectropriestSurv:33"),
)

MONTAGES = {m.key: m for m in (GRAFT, REAL, REAL_SURV)}

# --- alias RETRO-COMPATIBLES (le montage historique de la tranche 12) ---------------------------
SEED = GRAFT.seed
HOST = GRAFT.host
ALLY = GRAFT.ally
T_MAIN = GRAFT.target
FOE1, FOE2 = GRAFT.foe1, GRAFT.foe2
FOES = GRAFT.foes
MINE = GRAFT.mine


def weapon_reach(unit_id: str) -> tuple:
    """`(portee d'attaque, melee_only)` LUES dans `units.<kind>[id].weapons`.

    Mirror de la derivation de `catalog_inject._weapons` : une arme SANS champ `Range` est MELEE
    (`IsMelee = rng is None`, verifie exact sur les 175 entrees capturees), donc de portee 1 --
    l'adjacence. La portee du porteur est le MAX de ses armes. On ne la code pas en dur : c'est
    exactement ce qui differe entre le greffon (`tauMarksman`, une Pulse melee + une Piercing r3)
    et le porteur reel (une seule `Particle`, melee)."""
    pure = str(unit_id).split(":")[0]
    gc = G.unit(pure)
    if gc is None:
        raise MontageError(f"{pure!r} absent du gameconfig -- portee d'arme INDERIVABLE")
    ws = gc.get("weapons") or []
    if not ws:
        raise MontageError(f"{pure!r} n'a aucune arme au gameconfig -- il ne peut pas attaquer")
    ranges = [w.get("Range") for w in ws]
    return (max(int(r) if r else 1 for r in ranges), all(r is None for r in ranges))


def unit_movement(unit_id: str) -> int:
    """`Movement` du gameconfig -- le nombre de pas qui borne le movable set du caster."""
    pure = str(unit_id).split(":")[0]
    return int((G.unit(pure) or {}).get("Movement") or 0)


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError(f"pairUtility natif indisponible pour {tile} / cible {tgt}: {r}")
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError(f"le port ne produit AUCUNE action depuis {tile} sur {tgt}")
    return float(cand["u"])


def pair_port_muted(ctx, ab, tgt, tile) -> float:
    """Le port avec le playbook 1303 RETIRE du registre -- la reference qui isole le terme cote
    PORT, exactement comme le bras `base` l'isole cote NATIF."""
    import engine.playbook.psyker as PSY
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
    if saved is None:
        raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a isoler")
    try:
        return pair_port(ctx, ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


# --------------------------------------------------------------------------- seed BC (les 2 bras)

def _passives_after(path: str, host: str) -> list:
    """Les `PassiveAbilities` REELLEMENT ecrites dans l'entree de l'hote -- relues sur DISQUE.

    On ne fait jamais confiance au rapport d'un helper pour un bras dont tout depend : ce que le
    RPC va lire, c'est le fichier."""
    bc = json.loads(open(path, encoding="utf-8").read())
    for u in (bc.get("Units") or ()):
        if u.get("Id") == host:
            return list(u.get("PassiveAbilities") or ())
    raise MontageError(f"{host!r} absent de BC.Units du seed ecrit ({path})")


def _arm_file(prof: Montage, logs_dir: str, arm: str) -> str:
    """Un fichier par (montage, bras). `arm` est le bras APPARIE des qu'il vaut `base` ; tout autre
    nom designe le bras PORTEUR (le test historique passe `graft`, le CLI passe la cle du profil)."""
    which = "base" if arm == "base" else "carrier"
    return os.path.join(logs_dir, f"es_{prof.key}_{which}_seedbc.json")


def _seed_bc_graft(prof: Montage, logs_dir: str, arm: str) -> str:
    """Bras `graft` (1303 GREFFE sur un heros du pool) ou `base` (le MEME, moins 1303)."""
    out = _arm_file(prof, logs_dir, arm)
    p, reports = catalog_inject.write_grafted_seed_bc(
        out, [f"{prof.host}:{TriggeredAbilityType(ABILITY).name}"], replace=True)
    after = list((reports[0] or {}).get("passiveAbilitiesAfter") or ())
    if ABILITY not in after:
        raise MontageError(f"greffe RATEE : PassiveAbilities={after} ne contient pas {ABILITY}")
    if arm == "base":
        bc = json.loads(open(p, encoding="utf-8").read())
        for u in (bc.get("Units") or ()):
            if u.get("Id") == prof.host:
                u["PassiveAbilities"] = [a for a in after if a != ABILITY]
        open(p, "w", encoding="utf-8").write(json.dumps(bc))
    return str(p)


def _seed_bc_real(prof: Montage, logs_dir: str, arm: str) -> str:
    """Bras `real` (le npc avec SES passifs de gameconfig) ou `base` (les MEMES, moins 1303).

    L'entree de catalogue est injectee par `catalog_inject.augment` (bloc `Units` ET configs
    `Abilities` -- sans les secondes, l'unite se deploie et FAUTE au cast, verrou #226). Le bras
    `base` passe par `restrict_abilities`, qui DECLARE la restriction (`declare_graft`) : le BC
    porte alors MOINS que le gameconfig, et un port qui lirait le KIT au lieu de l'ENTITE monterait
    1303 quand meme (#448-r3-r1-r1)."""
    out = _arm_file(prof, logs_dir, arm)
    keep = None
    if arm == "base":
        # Les passifs du npc MOINS 1303 -- DERIVES de l'entree que `synthesize` produit, jamais
        # recopies a la main : le catalogue est la source, pas notre memoire de son kit.
        entry = catalog_inject.synthesize(prof.host)
        keep = {prof.host: ((), tuple(a for a in (entry.get("PassiveAbilities") or ())
                                      if a != ABILITY))}
    p, _added, _added_ab = catalog_inject.write_augmented_seed_bc(
        out, [prof.host], restrict_abilities=keep)
    after = _passives_after(str(p), prof.host)
    if (ABILITY in after) != (arm != "base"):
        raise MontageError(
            f"bras {arm} MAL ARME : PassiveAbilities={after} de {prof.host} "
            f"({'devrait' if arm != 'base' else 'ne devrait PAS'} contenir {ABILITY})")
    return str(p)


_SEED_BC = {"graft": _seed_bc_graft, "real": _seed_bc_real}


def seed_bc(logs_dir: str, arm: str, prof: Montage = GRAFT) -> str:
    p = _SEED_BC[prof.bc_kind](prof, logs_dir, arm)
    P380.assert_survives(p)
    return p


def build_args(logs_dir: str, arm: str, prof: Montage = GRAFT) -> list:
    """Les arguments `rl_duel build` du bras demande, SANS `--seed` ni `--state-file`.

    ⚠ `--unit-stat` patche par `VisualId` (pas par unitId) : un npc porte un suffixe de palier que
    le champ `VisualId` n'a pas. Il ecrase `Health` APRES la normalisation, donc APRES
    `explicitStats` -- ce qui est voulu : les stats explicites servent a faire ENTRER le porteur au
    pool (sans elles la formule heros leve et il finit dans `skipped`), les PV forces servent a ce
    que personne ne meure pendant le drive. Le terme mesure ne lit ni l'un ni l'autre."""
    stats = ";".join(f"{v}:Health={HP},RemainingHealth={HP}"
                     for v in (prof.visual, prof.ally) + prof.foes)
    return ["--board", prof.board, "--p-units", ",".join(prof.mine),
            "--a-units", ",".join(prof.foes),
            "--unit-stat", stats, "--seed-bc", seed_bc(logs_dir, arm, prof),
            *prof.build_extra]


# --------------------------------------------------------------------------- geometrie

def native_neighbours(t: tuple, cells: set, elev: dict) -> list:
    """Voisins de `t` au sens d'`IterateAdjacentTiles` : ring-1 hex AVEC la porte
    `|delta elevation| < 2`. Le voisinage NU (`hexgeo.neighbors`) sur-compte -- mesure #446, ou un
    temoin cru exclu par la portee l'etait deja par l'elevation, sans que rien ne le signale."""
    return [q for q in hexgeo.neighbors(t[0], t[1]) if q in cells and bq.is_adjacent(t, q, elev)]


def _garages(cells: list, elev: dict, busy: set, t: tuple, c: tuple, a: tuple) -> list:
    """Trois tuiles de PARKING : hors du voisinage natif de la cible (sinon elles verseraient un
    voisin au cran cense n'en avoir aucun), distinctes, mutuellement distantes, et jamais `A` --
    la tuile d'action doit rester LIBRE, sans quoi elle sort du movable set du caster."""
    d = hexgeo.distance
    picked = []
    for q in cells:
        if q in busy or q == a:
            continue
        if bq.is_adjacent(t, q, elev) or d(q, t) < 2 or d(q, c) < 2:
            continue
        if all(d(q, o) >= 2 for o in picked):
            picked.append(q)
        if len(picked) == 3:
            break
    return picked


def find_layout(cells: list, elev: dict, reach: int, melee_only: bool,
                origin: tuple | None = None,
                action_tiles: list | None = None) -> dict | None:
    """Cherche `(C, A, T, P1, P2, K1, K2, K3)` satisfaisant EXACTEMENT le regime decrit en tete.

    `C` = tuile de REPOS du caster ; `A` = tuile d'ACTION depuis laquelle la paire est evaluee.
    Contraintes posees depuis l'arbre natif :

      * `T` NON adjacente a `C` -- sinon le caster serait un voisin AMI permanent de sa propre
        cible : `c0` cesserait d'etre un « zero voisin », et `cF` cesserait d'etre le SEUL cran a
        porter un voisin ami, donc de discriminer `Enemies(caster)` de « voisins » ;
      * `A` a portee d'attaque de `T` (adjacence si l'arme est melee) et DANS les tuiles d'action
        du caster -- sans quoi `pairUtility` refuse la tuile (« ni courante ni dans le movable
        set ») ;
      * `P1`/`P2` deux autres tuiles voisines-NATIVES de `T` ;
      * `K1..K3` trois garages hors du voisinage de `T`.

    Un porteur a distance garde `A == C` (il tire sans bouger) : c'est le montage historique.

    ⚠ POUR UN PORTEUR MELEE, `A` EST PRISE DANS LES TUILES D'ACTION **MESUREES**, jamais dans un
    mirror offline du deplacement. Mesure du 2026-08-05 : un BFS `_move_ring` a `move` pas proposait
    `(0,2)` depuis `(3,4)` alors que le movable set natif ne la contient pas -- le pathfinder du jeu
    n'a pas le meme cout de terrain que le ring nu. Le montage echouait alors au 1er cran, avec
    raison. `C` est donc la position COURANTE du caster (il ne bouge jamais), et `A` sort de
    `ctx.action_tiles`."""
    d = hexgeo.distance
    cs = set(cells)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    order = sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2)
    if melee_only:
        if origin is None or not action_tiles:
            raise MontageError(
                "porteur MELEE : `find_layout` exige la position courante du caster ET ses tuiles "
                "d'action MESUREES -- un mirror offline du deplacement ne suffit pas")
        cands_c = [origin]
    else:
        cands_c = order
    for c in cands_c:
        # `A` doit etre une tuile d'action REELLE (movable set + position courante).
        reachable = [q for q in (action_tiles or ()) if q in cs] if melee_only else [c]
        for t in sorted(cells, key=lambda q: d(q, c)):
            if t == c or bq.is_adjacent(c, t, elev):
                continue
            nb = [q for q in native_neighbours(t, cs, elev) if q != c]
            if melee_only:
                # `A` = voisin de `T` ATTEIGNABLE ; il reste deux voisins pour les mobiles, donc
                # il en faut TROIS. On prend `A` le PLUS PROCHE du caster : plus la tuile est
                # proche, moins l'occupation ulterieure du plateau peut la sortir du movable set.
                pool = [q for q in reachable if q in nb]
                if not pool or len(nb) < 3:
                    continue
                a = min(pool, key=lambda q: d(q, c))
                rest = [q for q in nb if q != a]
            else:
                if not (2 <= d(c, t) <= reach) or len(nb) < 2:
                    continue
                a = c
                rest = nb
            p1, p2 = rest[0], rest[1]
            busy = {c, t, a, p1, p2}
            picked = _garages(order, elev, busy, t, c, a)
            if len(picked) < 3:
                continue
            return {"C": c, "A": a, "T": t, "P1": p1, "P2": p2,
                    "K1": picked[0], "K2": picked[1], "K3": picked[2]}
    return None


def attest_layout(case: dict, pos: dict) -> None:
    """RE-MESURE le regime sur les positions LIVE et refuse s'il n'est pas celui voulu."""
    d = hexgeo.distance
    ids, elev, lay = case["ids"], case["elev"], case["layout"]
    p = {k: pos.get(uid) for k, uid in ids.items()}
    missing = [k for k, v in p.items() if v is None]
    if missing:
        raise MontageError(f"montage NON INSTALLE : position inconnue pour {missing}")
    a = lay["A"]
    checks = [
        ("le caster est reste sur sa tuile de repos", p["C"] == lay["C"]),
        ("la cible est restee sur sa tuile", p["T"] == lay["T"]),
        # LE cran structurel : le caster ne doit JAMAIS etre un voisin de sa cible.
        ("T NON adjacente a C", not bq.is_adjacent(p["C"], p["T"], elev)),
        ("A a portee d'attaque de T",
         bq.is_adjacent(a, p["T"], elev) if case["melee_only"]
         else d(a, p["T"]) <= case["reach"]),
        # La tuile d'action doit rester LIBRE, sinon elle sort du movable set.
        ("A libre", a == p["C"] or a not in set(pos.values())),
    ]
    bad = [name for name, ok in checks if not ok]
    if bad:
        raise MontageError(f"montage NON INSTALLE : contraintes violees {bad} -- positions {p}, "
                           f"tuile d'action {a}")


# --------------------------------------------------------------------------- montage

def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _live_action_tiles(rpc, rid: int, dv: dict, cid: int) -> tuple:
    """`(position courante du caster, ses tuiles d'ACTION)` -- la liste `tiles` du tactic natif,
    position courante EN TETE (`engine.ai.context.action_tiles_for`, mirror de
    `ABaseAiUnitTactic$$GenerateActionTiles`). C'est la SEULE source admissible pour choisir une
    tuile d'action : `pairUtility` resout `col`/`row` dans le movable set natif et refuse tout le
    reste."""
    me = next((u for u in (dv.get("units") or ()) if u.get("id") == cid), None)
    pos = (me or {}).get("pos") or {}
    origin = (pos["col"], pos["row"]) if pos.get("col") is not None else None
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    mt = next((u for u in (mov.get("units") or ()) if u.get("unitId") == cid), None)
    return origin, _ai_ctx.action_tiles_for(origin, (mt or {}).get("tiles") or [])


def _roster(rpc, rid: int, prof: Montage) -> tuple:
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    ids = {}
    # ⚠ Le discriminant est le `VisualId`, et DEUX unitIds peuvent le partager : les deux npc
    # `admecNpc3Electropriest` / `...Surv` portent le MEME. Un `next(...)` choisirait le premier
    # en silence, donc peut-etre l'autre porteur -- on REFUSE plutot que de mesurer une unite
    # qu'on n'a pas designee.
    def _only(pool: list, vis: str, side: str) -> dict:
        got = [x for x in pool if x.get("visualId") == vis]
        if not got:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster {side}")
        if len(got) > 1:
            raise MontageError(
                f"montage AMBIGU : {len(got)} unites du roster {side} portent le VisualId {vis} "
                f"(ids {[x.get('id') for x in got]}) -- le montage ne peut pas dire laquelle il "
                f"mesure")
        return got[0]

    foe_pool = [x for x in units if x.get("owner") != myplayer and x.get("alive")]
    for key, vis in (("C", prof.visual), ("F", prof.ally)):
        ids[key] = _only(mine, vis, "ami")["id"]
    for key, vis in (("T", prof.target), ("E1", prof.foe1), ("E2", prof.foe2)):
        ids[key] = _only(foe_pool, vis, "adverse")["id"]
    return dv, ids, myplayer


def _attest_wired(rpc, rid: int, cid: int, expect_ability: bool, prof: Montage) -> list:
    """Moitie CABLAGE du patron #419 : 1303 est-il DANS l'`AbilitiesComponent` du caster ? Et
    quels AUTRES playbooks du registre y sont ? Le bras apparie neutralise ces derniers par
    difference, mais on les IMPRIME plutot que de les supposer absents.

    Le canal est `unitAbilityStates`, c.-a-d. l'ENTITE montee en bataille -- jamais le kit
    gameconfig, qui porte 1303 dans les DEUX bras du montage `real` (#448-r3-r1-r1)."""
    import engine.playbook.psyker as PSY
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live = sorted({i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                   for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)})
    has = ABILITY in live
    if has != expect_ability:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} {'absent' if expect_ability else 'PRESENT'} de "
            f"l'AbilitiesComponent de {prof.host} "
            f"(attendu {'present' if expect_ability else 'absent'})"
            f" -- triggered live lus = {live}")
    return [i for i in live if i in PSY.TRIGGERED_ATTACK_PLAYBOOKS and i != ABILITY]


def _normal_attacks(dv: dict, cid: int) -> list:
    """`[(abilityId, nom)]` des attaques NORMALES du caster, telles que la bataille les a montees.

    C'est l'autre moitie du bras apparie, et elle n'est PAS cosmetique : `ElectroShock` figure dans
    `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive`, donc retirer
    1303 retire AUSSI `ElectroShock_NormalAttack` (1178) et l'hote retombe sur son attaque par
    defaut. Les deux bras different donc par DEUX choses au niveau de l'entite -- ce qui serait
    fatal si `pairUtility` choisissait l'ability lui-meme. Il ne la choisit pas : on lui passe le
    MEME `abilityType` des deux cotes (celui du bras porteur), ce qui neutralise cet axe par
    construction. On le MESURE plutot que de le supposer."""
    me = next((u for u in (dv.get("units") or ()) if u.get("id") == cid), None)
    return sorted((a.get("id"), a.get("name"))
                  for a in ((me or {}).get("abilities") or ()) if a.get("kind") == "normal")


def stage(sid, rpc, rid: int, layout: dict | None, expect_ability: bool,
          prof: Montage = GRAFT) -> dict:
    """Installe le montage sur UN runner. `layout` fourni -> il est REJOUE a l'identique (c'est ce
    qui apparie les deux bras) ; `None` -> il est cherche sur le board."""
    elev, walk, _tid = P124._board(sid, rid)
    dv, ids, myplayer = _roster(rpc, rid, prof)
    others = _attest_wired(rpc, rid, ids["C"], expect_ability, prof)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    reach, melee_only = weapon_reach(prof.host)
    move = unit_movement(prof.host)
    origin, action = _live_action_tiles(rpc, rid, dv, ids["C"])
    lay = layout if layout is not None else find_layout(
        cells, elev, reach, melee_only, origin, action)
    if lay is None:
        raise MontageError(
            f"montage NON INSTALLE : aucune configuration (C,A,T,P1,P2,K1..K3) sur {prof.board} "
            f"pour "
            f"{prof.host} (portee {reach}, melee_only={melee_only}, move {move}) -- les quatre "
            f"crans ne seraient pas installables")
    return {"rid": rid, "cid": ids["C"], "ids": ids, "myplayer": myplayer, "dv": dv,
            "layout": lay, "walk": walk, "elev": elev, "other_playbooks": others,
            "profile": prof, "reach": reach, "melee_only": melee_only, "move": move,
            "origin": origin, "normals": _normal_attacks(dv, ids["C"])}


def place(sid, case: dict, step: str) -> dict:
    """Amene le cran `step` sur le runner de `case`, puis RE-MESURE les positions."""
    lay, ids = case["layout"], case["ids"]
    wanted = {
        "c0": {ids["C"]: lay["C"], ids["T"]: lay["T"],
               ids["F"]: lay["K1"], ids["E1"]: lay["K2"], ids["E2"]: lay["K3"]},
        "cF": {ids["C"]: lay["C"], ids["T"]: lay["T"],
               ids["F"]: lay["P1"], ids["E1"]: lay["K2"], ids["E2"]: lay["K3"]},
        "c1": {ids["C"]: lay["C"], ids["T"]: lay["T"],
               ids["F"]: lay["K1"], ids["E1"]: lay["P1"], ids["E2"]: lay["K3"]},
        "c2": {ids["C"]: lay["C"], ids["T"]: lay["T"],
               ids["F"]: lay["K1"], ids["E1"]: lay["P1"], ids["E2"]: lay["P2"]},
    }[step]
    if not P124._drive_to(sid, case["rid"], case["walk"], case["elev"], wanted):
        _dv, pos = P124._positions(sid, case["rid"])
        raise MontageError(f"cran {step} NON INSTALLE (runner {case['rid']}) : placement incomplet "
                           f"-- voulu {wanted}, obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, case["rid"], case["myplayer"])
    _dv2, pos = P124._positions(sid, case["rid"])
    attest_layout(case, pos)
    return pos


def derive_counts(pos: dict, ids: dict, elev: dict) -> tuple:
    """`(|ennemis du caster adjacents a T|, |amis du caster adjacents a T|)`, RE-DERIVES des
    positions live avec l'adjacence NATIVE. C'est l'arbitre du cran, jamais le port."""
    tp = pos.get(ids["T"])
    if tp is None:
        raise MontageError("cardinal NON DERIVABLE : position de la cible inconnue")
    foes = sum(1 for k in ("E1", "E2")
               if pos.get(ids[k]) is not None and bq.is_adjacent(tp, pos[ids[k]], elev))
    friends = sum(1 for k in ("C", "F")
                  if pos.get(ids[k]) is not None and bq.is_adjacent(tp, pos[ids[k]], elev))
    return foes, friends


# --------------------------------------------------------------------------- contre-epreuves

def measure_mutant_here(graft: dict, ab, tgt, tile, mutant: str, ref: float) -> dict:
    """Le port MUTE sur la geometrie COURANTE (le cran qui vient d'etre place)."""
    import engine.playbook.psyker as PSY
    from engine.playbook import electro_shock as ES
    from engine.playbook.fire_of_absolution import count_adjacent_by_camp

    class _Mut(ES.ElectroShockPlaybook):
        def calculate_attack_utility_in_steps(self, ctx, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            sc = getattr(ctx, "scene", None)
            if sc is None:
                return 0.0
            nf, ne = count_adjacent_by_camp(sc, attacker_uid, case_tgt_id)
            w = float(ctx.wt.triggered(WEIGHT_KEY))
            if mutant == "product":
                return w * ne
            if mutant == "any_neighbour":
                return w if (nf + ne) else 0.0
            if mutant == "no_gate":
                return w
            if mutant == "friends":
                return w if nf else 0.0
            raise AssertionError(mutant)

    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _Mut()
    try:
        got = pair_port(graft["ctx"], ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
    return {"mutant": mutant, "port": got, "port_ref": ref, "shift": got - ref}


def measure(sid, rpc, graft: dict, base: dict, weight: float, mutants: bool = False) -> tuple:
    """Un cran = un placement IDENTIQUE sur les deux bras, puis quatre nombres : `nat_graft`,
    `nat_base` (leur DIFFERENCE est le terme natif), `port` et `port_muted` (leur difference est le
    terme porte). Les contre-epreuves sont jouees PENDANT que le cran est installe -- un mutant ne
    peut pas etre rejoue apres coup, le `ctx` est celui de la geometrie courante."""
    rows, muts = [], []
    tile = graft["layout"]["A"]
    for step in STEPS:
        pos_g = place(sid, graft, step)
        pos_b = place(sid, base, step)
        foes_g, friends_g = derive_counts(pos_g, graft["ids"], graft["elev"])
        foes_b, _fb = derive_counts(pos_b, base["ids"], base["elev"])
        if foes_g != foes_b:
            raise MontageError(f"cran {step} DESAPPARIE : cardinal ennemi {foes_g} != {foes_b}")
        if foes_g != EXPECTED_COUNT[step]:
            raise MontageError(f"cran {step} NON INSTALLE : cardinal ennemi RE-DERIVE = {foes_g}, "
                               f"attendu {EXPECTED_COUNT[step]}")
        if step == "cF" and friends_g < 1:
            raise MontageError("cran cF NON DISCRIMINANT : aucun AMI adjacent a la cible")
        _dvg, ctx = _fresh_ctx(rpc, graft["rid"], graft["cid"])
        graft["ctx"] = ctx
        ab = next(iter(ctx.normal_ids or ()), None)
        if ab is None:
            raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
        if tile not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
            raise MontageError(f"cran {step} NON MESURABLE : tuile d'action {tile} hors des tuiles "
                               f"d'action du caster (movable set) -- vues = {ctx.action_tiles}")
        tgt = graft["ids"]["T"]
        # LA MEME tuile d'action des deux cotes : les bras partagent le layout, donc `A` aussi.
        nat_g = pair_native(rpc, graft["rid"], graft["cid"], tgt, ab, tile)
        nat_b = pair_native(rpc, base["rid"], base["cid"], base["ids"]["T"], ab, tile)
        port = pair_port(ctx, ab, tgt, tile)
        muted = pair_port_muted(ctx, ab, tgt, tile)
        rows.append({"step": step, "foes": foes_g, "friends": friends_g, "tile": tile, "ab": ab,
                     "native_graft": nat_g, "native_base": nat_b, "native_term": nat_g - nat_b,
                     "port": port, "port_muted": muted, "port_term": port - muted,
                     "expected": weight if foes_g else 0.0})
        if mutants:
            for m in MUTANTS:
                r = measure_mutant_here(graft, ab, tgt, tile, m, port)
                r["step"] = step
                muts.append(r)
    return rows, muts


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, seed: str, extra: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file du bras PORTEUR (celui qui a 1303)")
    ap.add_argument("--state-file-base",
                    help="chemin ABSOLU du state-file du bras APPARIE (defaut : <state-file>_base)")
    ap.add_argument("--montage", choices=sorted(MONTAGES), default="graft",
                    help="`graft` = 1303 greffe sur tauMarksman ; `real` = le porteur NPC lui-meme")
    ap.add_argument("--mutants", action="store_true",
                    help="joue les quatre contre-epreuves a CHAQUE cran (elles doivent MORDRE)")
    args = ap.parse_args()

    prof = MONTAGES[args.montage]

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    sf_g = args.state_file
    sf_b = args.state_file_base or (os.path.splitext(sf_g)[0] + "_base.json")
    logs = os.path.dirname(os.path.abspath(sf_g))
    os.makedirs(logs, exist_ok=True)

    rid_g = _build(sf_g, prof.seed, build_args(logs, prof.key, prof))
    rid_b = _build(sf_b, prof.seed, build_args(logs, "base", prof))
    graft = stage(sid, rpc, rid_g, None, True, prof)
    base = stage(sid, rpc, rid_b, graft["layout"], False, prof)
    lay = graft["layout"]
    weight = float(W.load().triggered(WEIGHT_KEY))
    if weight <= 0:
        raise MontageError(f"montage NON INSTALLE : le poids {WEIGHT_KEY} vaut {weight} dans le BC "
                           f"servi -- le terme serait nul et la mesure ne trancherait rien")
    print(f"montage {prof.key} | runners porteur={rid_g} base={rid_b} | {prof.host} "
          f"u{graft['cid']} @ {lay['C']} | portee {graft['reach']} "
          f"melee_only={graft['melee_only']} move {graft['move']} | poids {WEIGHT_KEY}={weight}")
    print(f"  layout T={lay['T']} A={lay['A']} P1={lay['P1']} P2={lay['P2']} "
          f"K1={lay['K1']} K2={lay['K2']} K3={lay['K3']}")
    print(f"  attaques normales : porteur={graft['normals']} base={base['normals']}")
    if graft["other_playbooks"]:
        print(f"  NB autres playbooks du registre sur le caster : {graft['other_playbooks']} "
              f"(neutralises par le bras apparie)")

    rows, muts = measure(sid, rpc, graft, base, weight, mutants=args.mutants)
    for r in rows:
        print(f"  [{r['step']}] foes={r['foes']} friends={r['friends']} ab={r['ab']} "
              f"natG={r['native_graft']:.6f} natB={r['native_base']:.6f} "
              f"TERME_NAT={r['native_term']:+.6f} | port={r['port']:.6f} "
              f"mute={r['port_muted']:.6f} TERME_PORT={r['port_term']:+.6f} "
              f"attendu={r['expected']:.6f}")
    for m in muts:
        print(f"  [mutant {m['mutant']:<13} @{m['step']}] deplacement du port = {m['shift']:+.9f} "
              f"({'MORD' if abs(m['shift']) > EPS else 'inerte'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
