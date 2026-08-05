"""#419-r1-tr14-r1 -- `HeavyBoltPistol` (1083) confronte sur ses DEUX PORTEURS REELS.

La tranche 14 a porte et confronte ce playbook par GREFFE sur `tauMarksman` (`case-92` §5bis
recours 3), faute de pouvoir amener en bataille ses porteurs : le npc `templNpc1Initiate` et le
summon d'ENVIRONNEMENT `templInitiate`. La greffe etait LEGITIME et c'etait LU (le corps ne
consulte du caster que son identite, sa position et le niveau de son propre passif), mais elle ne
couvrait ni les STATS, ni les TRAITS, ni l'ARME du porteur, et l'`Initiate` lui-meme n'avait jamais
ete en bataille. Ce probe ferme ce residu par le debloqueur de #419-r1-tr12-r2 :
`rl_duel build --explicit-stats <unitId>`, qui calcule les stats par le chemin natif de la CATEGORIE
du porteur au lieu de la formule HEROS (`IStatsFormula.StatsUsingProgressionIndexFor`, qui LEVE sur
eux et les range dans `skipped`).

## Les DEUX porteurs, et leurs regimes de stats -- qui ne sont PAS le meme

  `templNpc1Initiate:33`  npc    -> `UnitProgression$$GetNpcStats`, table `units.npc[id].stats[]`,
                                    palier = suffixe `:<n>` de l'id (`UnitNamingConventions$$
                                    GetLevelFromUnitId`). C'est un MIRROR DE CATALOGUE : ce que le
                                    jeu lui-meme ECRIT dans `BC.Units[]` pour un npc.
  `templInitiate`         summon -> `UnitProgression$$GetSummonStats`, variables `summon*` de
                                    l'ability invocatrice. C'est un MONTAGE : le jeu ecrit
                                    `Health = 0` au catalogue pour les 65 summons, et ces valeurs
                                    sont celles de l'etat POST-SPAWN
                                    (`SpawnUnitBehaviour$$GetStatsToOverride`).
                                    `catalog_inject.explicit_stats` NOMME la difference
                                    (`source = "npc"` contre `"summon-spawn"`), et ce probe la
                                    REPETE a chaque mesure -- confondre les deux ferait passer un
                                    montage pour un mirror.

`templInitiate` est declare par DEUX abilities (`EnvFactionSummons:BlackTemplars` et
`:SpaceWolves`), aux stats IDENTIQUES (3324/1330/665) : le choix de la voie ne change rien, et
`summon_stats` le MESURE avant de choisir plutot que de prendre la premiere en silence. Il n'est PAS
l'un des 9 summons hors portee des trois constantes de `GetSummonStats` (#419-r1-tr12-r2-r1) --
`templInitiatePyreblaster`, lui, l'est.

## Ce que le porteur REEL change par rapport a la greffe -- et ce qu'il ne change pas

| axe | greffe `tauMarksman` (tranche 14) | porteur reel |
|---|---|---|
| niveau / multiplicateur du passif | 50 / 180 (normalisation heros rank 17) | npc : 50 / 180 LUS dans `stats[33]` ; summon : 50 / (celui du BC) |
| montant `dmg` | `ability_var(HeavyBoltPistol, dmg, 50, 180)` | le MEME s'il porte le meme couple |
| arme | `Piercing`, portee 3 | `Chain`, 2 hits, MELEE (portee 1) |
| traits | ceux d'un HERO tau | `Imperial` + `NPC`, ou `Imperial` + `Summon` |
| grande alliance | Xenos | Imperial |
| profil de degat du TERME | `Bolter` (celui de l'ABILITY) | `Bolter` -- INCHANGE, et c'est la lecture 5 |

L'ARME est l'axe qui change le REGIME du montage, et il faut le dire : depuis une tuile a 2 hex, un
porteur MELEE ne peut pas frapper. Le composite d'attaque normale y est donc NUL, et le bras
apparie le MESURE (`native_base` a la tuile B). Ce n'est pas une degenerescence du TERME -- le
terme du passif, lui, y est PLEIN, parce que sa gate lit la position REELLE -- mais c'est un regime
different de celui de la tranche 14, ou l'hote portait une arme de portee 3.

## Le bras APPARIE -- identique a la tranche 14, a une ecriture pres

    `graft` : le porteur REEL, `PassiveAbilities = [1083]` -- son etat NATUREL, pas une greffe
    `base`  : le MEME, `PassiveAbilities = []` (`--unit-stat`, le levier de #446-r1 §4)

`terme_natif = natif_graft - natif_base` sur la MEME paire, la MEME tuile, la MEME geometrie.

⚠ Retirer 1083 change AUSSI l'attaque normale de l'entite : `1083 HeavyBoltPistol` est une cle de
`StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack` et rend
`1046 TemplarInitiateNormalAttack` (#419-r1-tr14-r5-r1). Le bras `base` retombe donc sur
`69 Loki_NormalAttack`. Les deux bras sont interroges avec la MEME `abilityType` -- celle du bras
`graft`, LUE et attestee = 1046 -- exactement comme la tranche 14. Et c'est un apport en soi : cette
entree de la table n'avait ete confrontee que par GREFFE sur `astraBullgryn` ; ici elle l'est sur son
porteur NATUREL.

## Les QUATRE crans (identiques a la tranche 14) et ce que chacun tranche

    cran                position REELLE de C   tuile d'attaque   terme attendu
    `far`               B (loin de T)          B                 = 0
    `tileAdj_realFar`   B (loin de T)          A (adjacente)     = 0   <- la gate IGNORE la tuile
    `adj`               A (adjacente a T)      A                 > 0
    `realAdj_tileFar`   A (adjacente a T)      B (loin de T)     > 0   <- la gate lit le REEL

Les deux DIAGONAUX sont LES crans : tous les autres playbooks attack portes qui gatent sur une
geometrie le font depuis la TUILE D'ATTAQUE ; celui-ci gate sur la position REELLE, parce que son
trigger DSL prend deux ENTITES (`IsAdjacentAbilityTrigger$$ShouldTrigger` -> slot 0x60
`BattleQuery$$AreEntitiesAdjacent` -> `MovementUtil$$AreTilesAdjacent(GetTiles(x), GetTiles(y))`).

Usage :
    python scripts/python/probe_419r1tr14r1_heavy_bolt_pistol_real_carriers.py \
        --carrier npc|summon --state-file <chemin ABSOLU> [--state-file-base <ABSOLU>] [--mutants]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419r1tr14r1_heavy_bolt_pistol_real_carriers_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject                                            # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P                    # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.entities.effects.magnitude import ability_var        # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.runner.abilities.attack_type import is_regular_attack  # noqa: E402
from engine.services.custom_normal_attack import CUSTOM_NORMAL_ATTACK_BY_PASSIVE  # noqa: E402

MontageError = P.MontageError
ABILITY = P.ABILITY                       # `TriggeredAbilityType.HeavyBoltPistol` = 1083
EPS = P.EPS
STEPS = P.STEPS

# Les six contre-epreuves de la tranche 14, PLUS une SEPTIEME qui n'existe que pour ce montage.
#
# ⚠ POURQUOI `profile_foreign` : sur le porteur REEL, `profile_weapon` (« et si le port lisait
# l'arme du caster ? ») est ALGEBRIQUEMENT INERTE -- l'arme de l'`Initiate` est `Chain` et
# l'ability porte `Bolter`, or les DEUX ont `PiercingRatio = 20` et la cible ne porte aucune
# limite de degat par profil. La faute que ce mutant simule est donc INOBSERVABLE sur ce porteur,
# et le rester en silence laisserait la lecture 5 (« le profil est celui de l'ABILITY ») SANS
# garde. `profile_foreign` la garde autrement : il force un profil dont le `PiercingRatio` DIFFERE
# -- choisi PAR MESURE, jamais ecrit en dur -- et doit MORDRE partout ou le terme existe.
# (La greffe `tauMarksman` de la tranche 14 etait, sur CET axe seulement, un meilleur
# discriminant : son arme `Piercing` porte `PiercingRatio = 80`.)
MUTANTS = P.MUTANTS + ("profile_foreign",)
# Mutants dont l'inertie sur CE montage est MESUREE et EXPLIQUEE (cf. la case-doc) : la garde les
# exige inertes plutot que de les taire.
INERT_BY_MEASURE = ("melee_from_real", "spread0", "profile_weapon")

BOARD = "MC1_67"
SEED = "141083"
ALLY = "necroWarden"                      # garage ami (n'entre dans aucun terme)
T_MAIN = "astraBullgryn"                  # la cible, FIXE dans tous les crans
FOE1 = "astraCreed"                       # garage ennemi
FOES = (T_MAIN, FOE1)
HP = 10000                                # personne ne meurt, et le composite `DamageDealt` reste
                                          # dans sa zone LINEAIRE (meme regime que la tranche 14).
                                          # SEUL `Health` est ecrase : `Damage`, `FixedArmor`,
                                          # `PassiveAbilityLevel` et le multiplicateur du porteur
                                          # restent ceux du chemin EXPLICITE, et le probe l'ATTESTE.

# `templInitiate` et `templNpc1Initiate` partagent leur `visualId` -- c'est LU au gameconfig, pas
# suppose (`GC.unit("templInitiate")["visualId"] == "templNpc1Initiate"`). Consequences : un seul
# des deux est deploye a la fois, et `--unit-stat` (qui matche par VisualId) ne peut donc pas les
# confondre.
CARRIERS = {
    "npc": {
        "unit": "templNpc1Initiate:33",   # palier 33 : `AbilityLevel` 50, `ProgressionIndex` 15
        "visual": "templNpc1Initiate",
        "source": "npc",                  # MIRROR DE CATALOGUE
        "trait": "NPC",
        # Pilotable par `applyAction move` : rien ne le rejoue entre deux `endturn`.
        "auto_played": False,
    },
    "summon": {
        "unit": "templInitiate",
        "visual": "templNpc1Initiate",
        "source": "summon-spawn",         # MONTAGE (etat post-spawn)
        "trait": "Summon",
        # AUTO-JOUE : `PlayAutomaticUnits` rejoue toute unite `Summon` au turn-start de sa team
        # (#291). On l'OBSERVE, on ne le COMMANDE pas -> placement ECRIT au build, zero `endturn`.
        "auto_played": True,
    },
}

# L'attaque normale que la fabrique substitue au porteur de 1083 -- LUE dans le mirror du
# dictionnaire statique, jamais ecrite en dur ici (#419-r1-tr14-r5-r1).
NORMAL_ATTACK_NAME = CUSTOM_NORMAL_ATTACK_BY_PASSIVE[TriggeredAbilityType.HeavyBoltPistol.name]
NORMAL_ATTACK_ID = int(ActiveAbilityType[NORMAL_ATTACK_NAME])     # 1046

# `GetVariableForLevel(cfg, 0xb, ...)` -- `AbilityVariableType.dmg`, la SEULE variable de la config.
_VAR_DAMAGE = AbilityVariableType.dmg.name


# --------------------------------------------------------------------------- seed / build

def build_args(carrier: str, arm: str) -> list:
    """Les arguments `rl_duel build` du bras demande, SANS `--seed` ni `--state-file`.

    Aucun seed BC ecrit : `--explicit-stats` injecte lui-meme l'entree de catalogue si elle manque
    (`catalog_inject.augment`), puis passe a `buildNormalizedBC` les champs calcules par le chemin
    natif de la categorie du porteur. Le bras `base` retire 1083 par `--unit-stat`, qui s'applique
    au BC deja NORMALISE -- c'est le levier de #446-r1 §4, et il ne touche RIEN d'autre.

    ⚠ Le PLACEMENT ECRIT (`--place` / `--a-place`) a ete essaye pour le porteur AUTO-JOUE et il est
    REFUSE ; le detail des quatre mesures est dans `steps_of`. Il n'est donc PAS propose ici : un
    parametre que rien n'exerce serait un piege.
    """
    spec = CARRIERS[carrier]
    stats = [f"{v}:Health={HP},RemainingHealth={HP}"
             for v in (spec["visual"], ALLY) + FOES]
    if arm == "base":
        stats.append(f"{spec['visual']}:PassiveAbilities=[]")
    elif arm != "graft":
        raise ValueError(f"bras inconnu : {arm!r}")
    return ["--board", BOARD,
            "--p-units", ",".join((spec["unit"], ALLY)),
            "--a-units", ",".join(FOES),
            "--explicit-stats", spec["unit"],
            "--unit-stat", ";".join(stats)]


# --------------------------------------------------------------------------- attestations

def expected_ability_state(carrier: str) -> dict:
    """Ce que le chemin EXPLICITE pose pour ce porteur -- calcule offline, mirror des deux chemins
    natifs. Sert de reference a l'attestation live : si la mesure ne le retrouve pas, le montage
    n'a PAS installe le porteur reel."""
    spec = CARRIERS[carrier]
    rep = catalog_inject.explicit_stats(spec["unit"])
    if rep["source"] != spec["source"]:
        raise MontageError(f"{spec['unit']} passe par le chemin {rep['source']!r}, attendu "
                           f"{spec['source']!r} -- npc et summon ne sont PAS le meme regime")
    f = rep["fields"]
    return {"source": rep["source"], "ability": rep.get("ability"), "fields": f,
            "passive_level": f.get("PassiveAbilityLevel"),
            "fixed_armor": f.get("FixedArmor"), "damage": f.get("Damage"),
            "health": f.get("Health")}


def attest_carrier(rpc, rid: int, cid: int, carrier: str, expect_ability: bool) -> dict:
    """RE-MESURE que l'entite en bataille EST le porteur reel, et rend ce qui pilote le terme.

    Quatre lectures, toutes LIVE :
      1. `configId` -- l'entite est bien celle de l'entree de catalogue demandee (jointure
         `BaseUnitComponent.Id` -> `UnitConfiguration.Id`, cf. `unitAbilityStates`) ;
      2. l'`AbilitiesComponent` porte (ou non) 1083, selon le bras -- la moitie CABLAGE du patron ;
      3. le couple `(level, multiplier)` du passif 1083, qui est EXACTEMENT ce que
         `TriggeredAbilityPlaybook<T>$$GetAbilityState(case.Caster)` transmet a
         `GetVariableForLevel` : c'est l'etage 1 de la decomposition du terme ;
      4. l'attaque normale que la fabrique a posee -- `1046 TemplarInitiateNormalAttack` sur le bras
         `graft` (la table de #419-r1-tr14-r5-r1, confrontee ici sur son porteur NATUREL) et
         `69 Loki_NormalAttack` sur le bras `base`.
    """
    spec = CARRIERS[carrier]
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    ents = st.get("units") or []
    if not ents:
        raise MontageError(f"montage NON INSTALLE : `unitAbilityStates` muet pour u{cid}")
    ent = ents[0]
    config_id = ent.get("configId")
    if config_id != spec["unit"]:
        raise MontageError(f"montage NON INSTALLE : l'entite u{cid} porte configId={config_id!r}, "
                           f"attendu {spec['unit']!r} -- ce n'est PAS le porteur reel")
    trig = {int((t.get("raw") or [None])[0]): t for t in (ent.get("triggered") or [])
            if isinstance((t.get("raw") or [None])[0], int)}
    has = ABILITY in trig
    if has != expect_ability:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} {'absent' if expect_ability else 'PRESENT'} de "
            f"l'AbilitiesComponent de {spec['unit']} (attendu "
            f"{'present' if expect_ability else 'absent'}) -- triggered lus = {sorted(trig)}")
    lvl = mult = None
    if has:
        lvl, mult = trig[ABILITY].get("level"), trig[ABILITY].get("mult")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    unit = next((u for u in (dv.get("units") or []) if u.get("id") == cid), None)
    normals = [a for a in ((unit or {}).get("abilities") or []) if a.get("kind") == "normal"]
    normal_id = normals[0].get("id") if normals else None
    expect_normal = NORMAL_ATTACK_ID if expect_ability else int(ActiveAbilityType.Loki_NormalAttack)
    if normal_id != expect_normal:
        raise MontageError(
            f"montage NON INSTALLE : l'attaque normale NATIVE de {spec['unit']} vaut {normal_id} "
            f"au lieu de {expect_normal} -- le dispatch de "
            f"`UnitFactory$$GetCustomNormalAttackTypeFromPassive` n'est pas celui attendu sur le "
            f"bras {'graft' if expect_ability else 'base'}")
    import engine.playbook.psyker as PSY
    others = [i for i in sorted(trig) if i in PSY.TRIGGERED_ATTACK_PLAYBOOKS and i != ABILITY]
    return {"configId": config_id, "level": lvl, "multiplier": mult, "normalAttack": normal_id,
            "ranged": (unit or {}).get("ranged"), "other_playbooks": others,
            "triggered": sorted(trig)}


def _roster(rpc, rid: int, carrier: str) -> tuple:
    spec = CARRIERS[carrier]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    ids = {}
    for key, vis in (("C", spec["visual"]), ("F", ALLY)):
        u = next((x for x in mine if x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster ami")
        ids[key] = u["id"]
    for key, vis in (("T", T_MAIN), ("E1", FOE1)):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        ids[key] = u["id"]
    return dv, ids, myplayer


def stage(sid, rpc, rid: int, carrier: str, layout: "dict | None", expect_ability: bool) -> dict:
    """Installe le montage sur UN runner. `layout` fourni -> REJOUE a l'identique (c'est ce qui
    apparie les deux bras) ; `None` -> cherche sur le board."""
    elev, walk, _tid = P124._board(sid, rid)
    _dv, ids, myplayer = _roster(rpc, rid, carrier)
    att = attest_carrier(rpc, rid, ids["C"], carrier, expect_ability)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = layout if layout is not None else P.find_layout(cells, elev)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration (T,A,B,K1,K2) sur {BOARD}")
    P.attest_layout(lay, elev)
    return {"rid": rid, "cid": ids["C"], "ids": ids, "myplayer": myplayer, "carrier": carrier,
            "layout": lay, "walk": walk, "elev": elev, "attest": att,
            "other_playbooks": att["other_playbooks"]}


# --------------------------------------------------------------------------- profils

def ability_profile_name() -> str:
    """`AbilityConfiguration$$GetDamageProfile(cfg)` du passif -- via le port LIVRE, pas une
    seconde derivation."""
    from engine.playbook.heavy_bolt_pistol import HeavyBoltPistolPlaybook
    return HeavyBoltPistolPlaybook._profile_name()


def _piercing(profile_name: str) -> int:
    import gameconfig as GC
    return int((GC.damage_profile(profile_name) or {}).get("PiercingRatio") or 0)


def weapon_profile_name(carrier: str) -> str:
    """Le profil de l'ARME du porteur -- MEME lecture que le mutant `profile_weapon` de la
    tranche 14 (`_mutant_class`), pour que la mesure d'equivalence porte sur ce qu'il fait."""
    import gameconfig as GC
    ws = (GC.unit(CARRIERS[carrier]["visual"]) or {}).get("weapons") or []
    ranged = [w for w in ws if w.get("Range")]
    return ((ranged or ws)[0] or {}).get("DamageProfile") or ""


def profile_equivalence(carrier: str) -> dict:
    """POURQUOI `profile_weapon` mord (ou non) sur ce porteur -- une MESURE, pas une hypothese.

    Le canal par lequel le profil entre dans la prediction est son `PiercingRatio` (plus l'index de
    profil, qui ne sert qu'aux limites de degat PAR PROFIL de la cible). Deux profils de meme ratio
    sont donc indistinguables tant que la cible n'en porte aucune : c'est un regime DEGENERE, et
    l'accord qu'il produit ne prouve rien.
    """
    ab, wp = ability_profile_name(), weapon_profile_name(carrier)
    return {"ability": ab, "ability_piercing": _piercing(ab),
            "weapon": wp, "weapon_piercing": _piercing(wp),
            "equivalent": _piercing(ab) == _piercing(wp)}


def foreign_profile() -> str:
    """Un profil de degat dont le `PiercingRatio` DIFFERE de celui de l'ability -- CHOISI PAR
    MESURE sur le gameconfig, jamais ecrit en dur : un littéral deviendrait faux au changement de
    build, et en silence."""
    from engine.playbook.prediction import _PROFILE_INDEX
    ref = _piercing(ability_profile_name())
    for name in sorted(_PROFILE_INDEX):
        if name == "None":
            continue
        if _piercing(name) != ref:
            return name
    raise MontageError("aucun profil de degat au `PiercingRatio` different de celui de l'ability "
                       "-- la contre-epreuve `profile_foreign` serait INERTE par construction")


def _foreign_profile_class(profile_name: str):
    """Sous-classe du port LIVRE dont SEULE la lecture du profil est retournee."""
    from engine.playbook import heavy_bolt_pistol as HB

    class _Mut(HB.HeavyBoltPistolPlaybook):
        @staticmethod
        def _profile_name() -> str:
            return profile_name

    return _Mut


def measure_mutant(ctx, ab, tgt, tile, mutant: str, ref: float, carrier: str) -> dict:
    """Un mutant sur la geometrie COURANTE. Route vers `_mutant_class` de la tranche 14 pour les
    six d'origine, et vers la classe locale pour `profile_foreign`."""
    if mutant != "profile_foreign":
        return P.measure_mutant_here(ctx, ab, tgt, tile, mutant, ref, CARRIERS[carrier]["visual"])
    import engine.playbook.psyker as PSY
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _foreign_profile_class(foreign_profile())()
    try:
        got = P.pair_port(ctx, ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
    return {"mutant": mutant, "port": got, "port_ref": ref, "shift": got - ref}


# --------------------------------------------------------------------------- etage PREDICTION

def native_prediction(rpc, rid, cid, tgt, ab, tile) -> dict:
    """`aiPlaybookPredict` natif -- les bornes de degat de l'ATTAQUE NORMALE a cette tuile."""
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": int(ab), "col": int(tile[0]),
                                  "row": int(tile[1])}, 90)
    if not (isinstance(r, dict) and r.get("ok")):
        raise MontageError(f"aiPlaybookPredict indisponible {tile}: {str(r)[:200]}")
    ev = [e for e in (r.get("events") or []) if e.get("targetId") == tgt]
    if not ev:
        return {"dmin": None, "dmax": None, "hits": None, "count": r.get("count")}
    return {"dmin": ev[0].get("healthDmgMin"), "dmax": ev[0].get("healthDmgMax"),
            "hits": ev[0].get("appliedHits"), "count": r.get("count")}


def port_prediction(scene, cid, tgt, tile) -> dict:
    from engine.playbook import prediction as PV
    out = PV.make_normal_attack_predictions(scene, cid, tgt, tile, meta=True)
    if not out:
        return {"dmin": None, "dmax": None, "hits": None}
    p = out[0].prediction
    ahd = p.accurate_health_damage
    return {"dmin": None if ahd is None else ahd.min, "dmax": None if ahd is None else ahd.max,
            "hits": getattr(p, "applied_hits", None)}


# --------------------------------------------------------------------------- mesure

def attest_traits(scene, cid: int, carrier: str) -> list:
    """Les traits d'ENTITE du porteur, RE-MESURES sur le substrat que le port consomme
    (`_entity_traits`, #316/#267-r1 -- `BC.Units[].Traits` monte en composant, jamais le kit).

    Le trait attendu est ce qui SEPARE les deux porteurs : `NPC` contre `Summon`, sur des kits par
    ailleurs identiques (memes `passiveAbilities`, meme `activeAbilities`, meme arme `Chain` a
    2 coups, meme `Movement` 3, meme `visualId`). Confondre les deux confondrait un mirror de
    catalogue avec un montage post-spawn.
    """
    from engine.playbook.prediction import _entity_traits
    got = list(_entity_traits(scene, cid) or ())
    want = CARRIERS[carrier]["trait"]
    if want is not None and want not in got:
        raise MontageError(f"montage NON INSTALLE : le porteur {CARRIERS[carrier]['unit']} ne "
                           f"porte PAS le trait {want!r} -- traits mesures = {got}")
    other = next(v["trait"] for k, v in CARRIERS.items() if k != carrier)
    if other is not None and other in got:
        raise MontageError(f"montage NON INSTALLE : le porteur {CARRIERS[carrier]['unit']} porte "
                           f"le trait {other!r} de l'AUTRE porteur -- traits mesures = {got}")
    return got


def attest_action_tiles(ctx, cid: int, carrier: str) -> list:
    """Les tuiles depuis lesquelles le caster peut etre EVALUE, et la BORNE qu'elles imposent.

    Pour un porteur AUTO-JOUE, `PlayAutomaticUnits` a deja consomme son tour au turn-start : il ne
    lui reste AUCUN deplacement, donc `aiMovableTiles` ne rend que sa tuile courante. C'est ce qui
    retire le cran `realAdj_tileFar` (tuile d'attaque a 2 hex) de son perimetre -- et c'est MESURE
    ici plutot que suppose. Si un summon se met a exposer d'autres tuiles, cette borne a change et
    la ligne rougit : le perimetre de `steps_of` doit alors etre re-instruit.
    """
    tiles = [tuple(t) for t in (ctx.action_tiles or []) if t and t[0] is not None]
    if CARRIERS[carrier]["auto_played"]:
        here = ctx.scene.pos(cid)
        if sorted(set(tiles)) != [tuple(here)]:
            raise MontageError(
                f"BORNE PERIMEE : le porteur AUTO-JOUE {CARRIERS[carrier]['unit']} expose "
                f"{sorted(set(tiles))} comme tuiles d'action au lieu de sa seule tuile courante "
                f"{tuple(here)} -- le perimetre de `steps_of` doit etre re-instruit")
    return sorted(set(tiles))


def attest_paired(sid, graft: dict, base: dict) -> dict:
    """LES DEUX BRAS SONT-ILS ENCORE APPARIES ? -- l'attestation SANS laquelle la difference
    `natif_graft - natif_base` ne mesure PAS le terme du passif.

    Un bras apparie ne l'est que tant que les deux runners portent le MEME etat. MESURE
    (montage summon, premiere version) : le porteur AUTO-JOUE attaque la cible pendant les
    `endturn` du pilotage, et il l'attaque PLUS FORT du cote `graft` (c'est precisement ce que le
    passif ajoute) -- la cible finissait a des PV DIFFERENTS dans les deux bras, et la difference
    des deux `pairUtility` melangeait le terme et un ecart d'ETAT. L'ecart alors lu (-2.775445)
    n'accusait pas le port.

    On confronte donc les PV de TOUTES les unites appariees (le caster, la cible, les deux
    garages), et on rougit au premier ecart.
    """
    _dvg, posg = P124._positions(sid, graft["rid"])
    _dvb, posb = P124._positions(sid, base["rid"])
    dvg = P124._r(sid, "decisionView", {"runnerId": graft["rid"], "allAbilities": True}, 150)
    dvb = P124._r(sid, "decisionView", {"runnerId": base["rid"], "allAbilities": True}, 150)
    hpg = {u["id"]: u.get("hp") for u in (dvg.get("units") or [])}
    hpb = {u["id"]: u.get("hp") for u in (dvb.get("units") or [])}
    bad = {}
    for key, gid in graft["ids"].items():
        bid = base["ids"][key]
        if hpg.get(gid) != hpb.get(bid) or posg.get(gid) != posb.get(bid):
            bad[key] = {"graft": (hpg.get(gid), posg.get(gid)),
                        "base": (hpb.get(bid), posb.get(bid))}
    if bad:
        raise MontageError(
            f"BRAS NON APPARIES : (hp, pos) divergent entre les deux runners -- {bad}. La "
            f"difference `natif_graft - natif_base` melangerait le terme du passif et un ecart "
            f"d'ETAT ; aucune mesure n'est valide dans ce regime")
    return {"hp": hpg, "pos": posg}


def measure(sid, rpc, graft: dict, base: dict, mutants: bool = False, steps=STEPS) -> tuple:
    """Un cran = un emplacement IDENTIQUE sur les deux bras + une tuile d'attaque, puis quatre
    nombres : `nat_graft`, `nat_base` (leur DIFFERENCE est le terme natif), `port` et `port_muted`.

    `nat_base` est AUSSI le TEMOIN DE SUBSTRAT du cran : il dit si le composite d'attaque normale
    produit quelque chose depuis cette tuile INDEPENDAMMENT du passif. Un cran dont les DEUX bras
    sont nuls est nomme DEGENERE dans la sortie -- l'accord y est vrai mais ne prouve rien.
    """
    carrier = graft["carrier"]
    rows, muts = [], []
    placed = None
    for step, spot, tile_key, expect_term in steps:
        if placed != spot:
            P.place(sid, graft, spot)
            P.place(sid, base, spot)
            placed = spot
        attest_paired(sid, graft, base)
        lay = graft["layout"]
        tile = lay[tile_key]
        _dvg, ctx = P._fresh_ctx(rpc, graft["rid"], graft["cid"])
        graft["ctx"] = ctx
        if "traits" not in graft:
            graft["traits"] = attest_traits(ctx.scene, graft["cid"], carrier)
            graft["action_tiles"] = attest_action_tiles(ctx, graft["cid"], carrier)
        ab = next(iter(ctx.normal_ids or ()), None)
        if ab is None:
            raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
        if int(ab) != NORMAL_ATTACK_ID:
            raise MontageError(f"montage NON INSTALLE : l'attaque normale du bras graft vaut {ab}, "
                               f"attendu {NORMAL_ATTACK_ID} ({NORMAL_ATTACK_NAME})")
        if not is_regular_attack(int(ab)):
            raise MontageError(f"montage NON DISCRIMINANT : l'attaque normale {ab} n'est pas dans "
                               f"`REGULAR_ATTACK_ABILITY_TYPES` -- la gate du corps natif couperait "
                               f"le terme a TOUS les crans")
        if tile not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
            raise MontageError(f"cran {step} NON MESURABLE : tuile {tile} hors des tuiles d'action "
                               f"du caster (emplacement {spot})")
        tgt = graft["ids"]["T"]
        nat_g = P.pair_native(rpc, graft["rid"], graft["cid"], tgt, ab, tile)
        nat_b = P.pair_native(rpc, base["rid"], base["cid"], base["ids"]["T"], ab, tile)
        port = P.pair_port(ctx, ab, tgt, tile)
        muted = P.pair_port_muted(ctx, ab, tgt, tile)
        # ETAGE PREDICTION, mesure SEPAREE de l'etage utilite (jamais fitter un scalaire) : les
        # bornes de degat de l'ATTAQUE NORMALE a cette tuile, natif contre port. C'est ce qui
        # SITUE tout ecart de NIVEAU -- un ecart deja present ici ne se corrige pas dans le
        # composite. Prise sur le bras `base` : sans le passif, l'attaque normale est pure.
        pred_nat = native_prediction(rpc, base["rid"], base["cid"], base["ids"]["T"], ab, tile)
        pred_port = port_prediction(ctx.scene, graft["cid"], tgt, tile)
        rows.append({"step": step, "spot": spot, "tile": tile, "ab": int(ab),
                     "expect_term": expect_term,
                     "native_graft": nat_g, "native_base": nat_b, "native_term": nat_g - nat_b,
                     "port": port, "port_muted": muted, "port_term": port - muted,
                     "pred_native": pred_nat, "pred_port": pred_port,
                     # DEGENERE = les deux bras nuls : le cran ne porte alors aucune information,
                     # ni sur la gate ni sur le montant. Nomme, jamais tu.
                     "degenerate": abs(nat_g) < EPS and abs(nat_b) < EPS})
        if mutants:
            for m in MUTANTS:
                r = measure_mutant(ctx, ab, tgt, tile, m, port, carrier)
                r["step"] = step
                muts.append(r)
    return rows, muts


def expected_damage(att: dict) -> "int | None":
    """Etage 1 de la decomposition : le montant `dmg` que le corps natif predit, derive du couple
    `(level, multiplier)` MESURE sur l'entite. C'est ce qui explique tout ecart de terme entre deux
    porteurs -- on ne fitte jamais le scalaire, on le DECOMPOSE."""
    if att.get("level") is None:
        return None
    return ability_var(TriggeredAbilityType.HeavyBoltPistol.name, _VAR_DAMAGE, att["level"],
                       multiplier_pct=int(att.get("multiplier") or 100))


# --------------------------------------------------------------------------- orchestration

def _build(state_file: str, extra: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _dispose(state_file: str) -> None:
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", state_file],
                   cwd=_HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")


def steps_of(carrier: str) -> tuple:
    """Les crans ATTEIGNABLES pour ce porteur -- et, par difference avec `STEPS`, ceux qui ne le
    sont pas. Ce n'est pas un choix de confort : c'est une BORNE MESUREE.

    Un porteur AUTO-JOUE (`Summon`) n'a AUCUN cran atteignable, et ce sont QUATRE mesures qui le
    disent -- pas une renonciation. D'abord, les deux voies de placement lui echappent :

      * `applyAction move` -- `PlayAutomaticUnits` le rejoue au turn-start de sa team (#291) et le
        ramene au contact. MESURE : un `_drive_to` vers la tuile a 2 hex rend `(0,1)` au lieu de
        `(0,2)`. On l'OBSERVE, on ne le COMMANDE pas ;
      * `--place` (`AddUnitMessage` -> `IdunBattle.Operations.AddUnitOperation$$Execute`) -- REFUSE.
        MESURE par BRAS APPARIE, seul le trait changeant : `necroWarden` sans `Summon` est place a
        `(0,2)` (« placements verifies OK »), le MEME `necroWarden` avec `Summon` greffe
        (`catalog_inject.write_trait_seed_bc`) apparait a `(1,5)` -- le placement ecrit est
        DETOURNE. Sur `templInitiate` le meme montage rend « non deploye ».

    Une TROISIEME borne, du meme fait, retire les crans DIAGONAUX : un summon deja joue par
    `PlayAutomaticUnits` n'a plus de mouvement, donc `aiMovableTiles` ne rend que SA TUILE
    COURANTE (`attest_action_tiles` le MESURE et fait ROUGIR si ce n'est plus vrai). Or une
    diagonale exige, par definition, une tuile d'attaque DIFFERENTE de la position reelle.

    Une QUATRIEME, enfin, retire les deux crans ALIGNES eux-memes : le bras apparie se ROMPT. Le
    summon attaque la cible a chaque turn-start, et il l'attaque PLUS FORT du cote `graft` -- c'est
    precisement ce que le passif ajoute. MESURE : la cible finit a des PV DIFFERENTS dans les deux
    runners, donc `natif_graft - natif_base` melange le terme et un ecart d'ETAT (l'ecart lu dans
    ce regime, -2.775445, n'accusait pas le port). Le contournement « placer LA CIBLE au lieu du
    caster » ne sauve rien : `--a-place` sort les deux a-units de `BC.PredefinedUnits` et INVERSE
    les camps -- le summon devient l'IA, joue immediatement et blesse la cible (HP 9368 sur 10000,
    mesure).

    Le porteur SUMMON n'a donc AUCUN cran de terme confrontable ; `run_case_summon` le DEMONTRE
    plutot que de l'affirmer. Les quatre crans le sont sur le porteur NPC, qui partage avec lui son
    `visualId`, son arme (`Chain`, 2 coups), son `Movement` 3, ses `passiveAbilities`, ses
    `activeAbilities` et son attaque normale native -- et ce qu'ils tranchent (la gate lit le REEL,
    pas la tuile) ne lit aucune stat, aucun trait, aucune arme.
    """
    if not CARRIERS[carrier]["auto_played"]:
        return STEPS
    return ()


def run_case(sid, rpc, carrier: str, sf_g: str, sf_b: str, mutants: bool = False,
             builder=None) -> dict:
    """Monte le montage complet et rend `{layout, rows, muts, graft, base, wiring, skipped}`.

    DEUX regimes, et c'est le TRAIT du porteur qui tranche (cf. `steps_of`) :

      * PILOTABLE (npc) -- une paire de runners, les QUATRE crans, unites conduites par
        `applyAction move` : le montage de la tranche 14 ;
      * AUTO-JOUE (`Summon`) -- le caster ne bouge pas et c'est LA CIBLE qu'on place
        (`--a-place`), une paire de runners PAR CRAN, et **AUCUN `endturn`**. Ce dernier point
        n'est pas une precaution : avec des `endturn`, le summon attaque la cible, et il l'attaque
        PLUS FORT du cote `graft` -- les deux bras cessent d'etre apparies et la difference cesse
        de mesurer le terme (`attest_paired` le montre).

    L'appelant dispose `sf_g`/`sf_b`.
    """
    mk = builder or _build
    steps = steps_of(carrier)
    skipped = tuple(s[0] for s in STEPS if s not in steps)
    if not CARRIERS[carrier]["auto_played"]:
        rid_g = mk(sf_g, build_args(carrier, "graft"))
        rid_b = mk(sf_b, build_args(carrier, "base"))
        graft = stage(sid, rpc, rid_g, carrier, None, True)
        base = stage(sid, rpc, rid_b, carrier, graft["layout"], False)
        rows, muts = measure(sid, rpc, graft, base, mutants=mutants, steps=steps)
        return {"layout": graft["layout"], "rows": rows, "muts": muts, "graft": graft,
                "base": base, "steps": steps, "skipped": skipped, "montage": "caster-drive",
                "paired": True, "divergence": None,
                "wiring": {"ctx": graft["ctx"], "row": rows[-1], "cid": graft["cid"],
                           "tgt": graft["ids"]["T"]}}

    return run_case_summon(sid, rpc, carrier, sf_g, sf_b, builder=builder)


def run_case_summon(sid, rpc, carrier: str, sf_g: str, sf_b: str, builder=None) -> dict:
    """Le porteur SUMMON : ce qui est CONFRONTE, et la DEMONSTRATION de ce qui ne l'est pas.

    Le terme du passif n'est PAS mesurable de facon APPARIEE sur ce porteur, et ce probe ne se
    contente pas de l'affirmer -- il l'EXECUTE et rend la divergence chiffree :

      1. le porteur ARRIVE en bataille avec ses propres stats (chemin `summon-spawn`), son trait
         `Summon`, son couple `(level, multiplier)` et son attaque normale native -- tout cela est
         mesure (`attest_carrier`, `attest_traits`) ;
      2. il n'expose plus AUCUNE tuile d'action hors la sienne (`attest_action_tiles`), donc les
         deux crans DIAGONAUX sont hors de portee par construction ;
      3. et le bras apparie se ROMPT : on pilote la geometrie comme pour le npc, puis
         `attest_paired` est appele -- il DOIT lever, parce que le summon, joue par
         `PlayAutomaticUnits` a chaque turn-start, attaque la cible PLUS FORT du cote `graft`
         (c'est exactement ce que le passif ajoute). La divergence de PV est rendue telle quelle.

    Si `attest_paired` NE leve PAS, le regime a change : le probe le dit, et le residu doit etre
    re-instruit. On ne rend jamais un « non confrontable » qu'on n'a pas re-mesure.
    """
    mk = builder or _build
    rid_g = mk(sf_g, build_args(carrier, "graft"))
    rid_b = mk(sf_b, build_args(carrier, "base"))
    graft = stage(sid, rpc, rid_g, carrier, None, True)
    base = stage(sid, rpc, rid_b, carrier, graft["layout"], False)
    P.place(sid, graft, "A")
    P.place(sid, base, "A")
    _dvg, ctx = P._fresh_ctx(rpc, graft["rid"], graft["cid"])
    graft["ctx"] = ctx
    graft["traits"] = attest_traits(ctx.scene, graft["cid"], carrier)
    graft["action_tiles"] = attest_action_tiles(ctx, graft["cid"], carrier)
    paired, divergence = True, None
    try:
        attest_paired(sid, graft, base)
    except MontageError as e:
        paired, divergence = False, str(e)
    return {"layout": graft["layout"], "rows": [], "muts": [], "graft": graft, "base": base,
            "steps": (), "skipped": tuple(s[0] for s in STEPS), "montage": "unpairable",
            "paired": paired, "divergence": divergence, "wiring": None}


# --------------------------------------------------------------------------- CLI


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--carrier", choices=sorted(CARRIERS), default="npc",
                    help="le porteur REEL a confronter (npc = mirror de catalogue ; "
                         "summon = MONTAGE de l'etat post-spawn)")
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file du bras GREFFE")
    ap.add_argument("--state-file-base",
                    help="chemin ABSOLU du state-file du bras APPARIE (defaut : <state-file>_base)")
    ap.add_argument("--mutants", action="store_true",
                    help="joue les six contre-epreuves a CHAQUE cran")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    carrier = args.carrier
    spec = CARRIERS[carrier]
    exp = expected_ability_state(carrier)
    print(f"porteur REEL {spec['unit']} ({carrier}) -- chemin {exp['source']}"
          + (f" via {exp['ability']}" if exp.get("ability") else ""))
    print(f"  stats du chemin explicite : hp={exp['health']} dmg={exp['damage']} "
          f"fixedArmor={exp['fixed_armor']} passiveAbilityLevel={exp['passive_level']}")
    if exp["source"] == "summon-spawn":
        print("  [MONTAGE] le jeu ecrit 0 au catalogue pour un summon : ces stats sont celles du "
              "SPAWN, pas du catalogue")

    sf_g = args.state_file
    sf_b = args.state_file_base or (os.path.splitext(sf_g)[0] + "_base.json")
    os.makedirs(os.path.dirname(os.path.abspath(sf_g)), exist_ok=True)

    pe = profile_equivalence(carrier)
    print(f"  PROFILS : ability={pe['ability']}(PiercingRatio {pe['ability_piercing']}) "
          f"arme={pe['weapon']}(PiercingRatio {pe['weapon_piercing']}) -> "
          + ("EQUIVALENTS : la contre-epreuve `profile_weapon` est ALGEBRIQUEMENT INERTE sur ce "
             f"porteur ; `profile_foreign` la remplace avec {foreign_profile()}"
             if pe["equivalent"] else "DISTINCTS : `profile_weapon` est discriminant"))

    case = run_case(sid, rpc, carrier, sf_g, sf_b, mutants=args.mutants)
    graft, base, lay = case["graft"], case["base"], case["layout"]
    att = graft["attest"]
    print(f"runners graft={graft['rid']} base={base['rid']} | {spec['unit']} u{graft['cid']} "
          f"| montage={case['montage']}")
    if case["skipped"]:
        print(f"  NON CONFRONTES sur ce porteur : {list(case['skipped'])} -- porteur AUTO-JOUE "
              f"(`PlayAutomaticUnits`, #291), placement ecrit REFUSE par le natif, plus aucune "
              f"tuile d'action hors la sienne, et bras apparie ROMPU (cf. `steps_of`). Ces crans "
              f"le sont sur le npc.")
    if case["montage"] == "unpairable":
        print(f"  action_tiles du caster = {graft.get('action_tiles')} (sa seule tuile courante)")
        if case["paired"]:
            print("  (!) REGIME CHANGE : `attest_paired` N'A PAS leve -- le bras apparie tient "
                  "maintenant sur ce porteur, le residu doit etre RE-INSTRUIT")
        else:
            print(f"  DEMONSTRATION du non-appariement : {case['divergence']}")
    print(f"  layout {lay}")
    print(f"  ATTESTE : configId={att['configId']} traits={graft.get('traits')} "
          f"passif1083 level={att['level']} mult={att['multiplier']} "
          f"-> dmg={expected_damage(att)} | attaque normale NATIVE={att['normalAttack']} "
          f"({NORMAL_ATTACK_NAME}) | ranged={att['ranged']}")
    print(f"  bras base : attaque normale NATIVE={base['attest']['normalAttack']} "
          f"(Loki_NormalAttack)")
    if graft["other_playbooks"]:
        print(f"  NB autres playbooks du registre sur le caster : {graft['other_playbooks']} "
              f"(neutralises par le bras apparie)")

    rows, muts = case["rows"], case["muts"]
    for r in rows:
        print(f"  [{r['step']:<16}] spot={r['spot']} tile={r['tile']} "
              f"natG={r['native_graft']:.6f} natB={r['native_base']:.6f} "
              f"TERME_NAT={r['native_term']:+.6f} | port={r['port']:.6f} "
              f"mute={r['port_muted']:.6f} TERME_PORT={r['port_term']:+.6f} "
              f"ecart={r['port_term'] - r['native_term']:+.9f}"
              + ("   [DEGENERE : les deux bras nuls]" if r["degenerate"] else ""))
        pn, pp = r["pred_native"], r["pred_port"]
        print(f"      etage PREDICTION (attaque normale, bras base) : "
              f"natif {pn['dmin']}..{pn['dmax']} ({pn['hits']} coups) | "
              f"port {pp['dmin']}..{pp['dmax']} ({pp['hits']} coups)")
    for m in muts:
        print(f"  [mutant {m['mutant']:<16} @{m['step']:<16}] deplacement du port = "
              f"{m['shift']:+.9f} ({'MORD' if abs(m['shift']) > EPS else 'inerte'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
