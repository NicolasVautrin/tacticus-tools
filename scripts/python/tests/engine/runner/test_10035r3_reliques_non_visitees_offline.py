"""#10035-r3 -- les 23 reliques qui n'avaient AUCUNE entree `ABILITY_INIT_OWNER_EFFECTS`.

CE QUE LE RESIDU DISAIT : << le zero n'est pas une mesure, c'est une absence de lecture >>. Les 23
`CreateBehaviour`/`CreateTrigger` ont ete LUS sur `t6dpr4k06g`. **SEPT** posent un owner-effect a
l'INIT ; **SEIZE** n'en posent aucun -- et ce resultat NEGATIF compte autant, parce que c'est lui
qui empeche de croire qu'on aurait pu tout inscrire au hasard. Ce fichier fige les deux.

LES DEUX FORMES, ramenees au MEME patron natif :
  (a) base `AOwnerEffectTriggeredAbility` / `AOwnerEffectSpecificTriggeredAbility` -- la classe ne
      declare que `GetEffectType` (corps ENTIER `return <ordinal>`), le reste vient de la base :
      `$$CreateTrigger` = `OnOwnerSpecificAbilityInit(this.AbilityType@+0x10)` et
      `$$CreateBehaviour` = `If(<ce trigger>, AddEffect(GetEffectType(), AbilityState(Owner,
      AbilityType), targets = Owner@<DSLSelectors+0x30>, turns = ZEROE -> PERMANENT), null)`.
  (b) `BaseTriggeredAbility` + `CreateBehaviour` PROPRE, dont le `CreateTrigger` est un corps
      ICF PARTAGE de corps ENTIER `OnOwnerSpecificAbilityInit(this.get_AbilityType())`.

⚠ LE PARTAGE ICF DE (b) EST MESURE, PAS DEDUIT. Le RPC `resolveMethodPtr` (lecture pure, aucun
runner) rend le MEME `methodPointer` pour les `CreateTrigger` de `RelicBoltPistolAbility`,
`SupaCyborkBodyAbility_AddTrait`, `DawnBlade_InitAbility` et `WayOfTheShortBlade_InitAbility` --
et c'est cette derniere qui porte le symbole, donc le corps lisible.

⚠ CE FICHIER EST OFFLINE : `load_state` avec un payload `unitAbilityStates` FABRIQUE, sans runner.
La confrontation LIVE de la POSE elle-meme est deja gardee par
`test_10035_pose_tertiaire_au_chargement_offline.py` (le RANG des passes) et par les probes de
relique ; ce qui manquait, c'est le CONTENU du registre.

ASCII only.
"""
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import pytest                                                              # noqa: E402

import hexgeo                                                              # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects import factory as F                           # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "L'etage 0 fige les ordinaux LUS au decompile (0x5aa/0x5ab/0x5ad/0x5b1/0x5b2/0x5b5/"
              "0x5bc/0x5db/0x5dc/0x5dd) : un renumerotage du build les rendrait faux sans toucher "
              "aucun des chemins ci-dessus.",
}

COLS, ROWS = 8, 8
HP = 90000
NIVEAU_TERTIAIRE, MULT_TERTIAIRE = 3, 100
NIVEAU_PASSIF, MULT_PASSIF = 50, 180
ENNEMI = 90

#: Les SEPT reliques qui POSENT, avec un porteur AUTORISE (`catalog_inject.relic_carriers`),
#: l'ordinal de leur `TriggeredAbilityType` et les owner-effects LUS.
POSEUSES = (
    (11, "admecMarshall",  "KardiocoreGalvanus", 1457, ("KardiocoreGalvanus_ExtraCritDmg",)),
    (12, "tyranParasite",  "MawClawsOfThyrax",   1469, ("MawClawsOfThyrax_ExtraCritDmg",)),
    (13, "orksRuntherd",   "SupaCyborkBody",     1475, ("SupaCyborkBody_CritDmgReduction",)),
    (14, "worldJakhal",    "TalismanOfRage",     1460, ("TalismanOfRage_CritDamageReduction",)),
    (15, "eldarAutarch",   "PhoenixGem",         1458, ("PhoenixGem_CanRevive",)),
    (16, "tauFarsight",    "DawnBlade",          1501, ("DawnBlade_ExtraDmg",)),
    (17, "ultraTitus",     "RelicBoltPistol",    1467, ("RelicBoltPistol_ExtraPierce",
                                                       "RelicBoltPistol_ExtraCritDamage")),
)

#: Les SEIZE reliques dont la lecture a rendu NON -- le resultat NEGATIF, et la raison LUE.
#: Sans cette liste, l'etage 1 serait un vert-sur-rien : n'importe quel sur-ajout y passerait.
NON_POSEUSES = {
    "BladeOfTheAncestors":     "AddEffect(Owner) mais sous `On(0x0 = UnitDeath)`, pas un init",
    "BookOfFate":              "AddStaticStatModifierEffect sur AUTRUI (Daemon adjacent), `On(NormalAttack)`",
    "ChaliceOfBaal":           "AddEffect sur AUTRUI (UnitsAffectedByHealType), `On(UnitDeath)`",
    "DaemonfleshPlate":        "AddEffect(Owner) mais dans la branche `then` d'un `If`, `On(Attack)`",
    "Dw02AdvancedBurstCannon": "AddStaticStatModifierEffect(Caster), `On(Attack)` + `If`",
    "Helspear":                "AddEffect sur Target et sur Tiles(Target), `On(Attack)`",
    "Lakrimae":                "AddEffect(Contaminated) sur TargetTiles, `On(NormalAttack)`",
    "Maugetar":                "AddEffect(Owner) inconditionnel mais sous `On(0x12 = TurnStart_"
                               "EffectActivation)` : une re-pose PAR TOUR, pas une pose a l'init",
    "ParagonSpear":            "aucun AddEffect (AttackWithAttackDamage seul)",
    "PhasalSubjugator":        "aucun AddEffect (Spawn / TriggerAbility)",
    "RelicOfLostCadia":        "AddEffect sur AUTRUI (IsImperialAndSummon), sous un `If` a deux branches",
    "RelicPowerFist":          "AddEffect(Pinned/Stunned) sur Target, sous `Maybe(...)`",
    "SabreOfSacrifice":        "AddEffect(Pinned) sur Target, `On(Attack) & IsCharging`",
    "TalonOfHorus":            "ni CreateBehaviour ni CreateTrigger propres (stubs partages)",
    "VolummsMasterArtifice":   "aucun AddEffect (Heal / persistent data), `On(UnitRepaired)`",
    "WyrdmakersHelm":          "AddEffect(Ice) sur des TUILES, `On(UnitHealedWithRemoveEffects)`",
}

#: Les ordinaux LUS au decompile, cote `EffectType`, par ability.
ORDINAUX_EFFET = {
    "KardiocoreGalvanus_ExtraCritDmg":     0x5aa,
    "MawClawsOfThyrax_ExtraCritDmg":       0x5b5,
    "SupaCyborkBody_CritDmgReduction":     0x5bc,
    "TalismanOfRage_CritDamageReduction":  0x5ad,
    "PhoenixGem_CanRevive":                0x5ab,
    "DawnBlade_ExtraDmg":                  0x5dd,
    "RelicBoltPistol_ExtraPierce":         0x5b1,
    "RelicBoltPistol_ExtraCritDamage":     0x5b2,
    "WayOfTheShortBlade_DamageBuff":       0x5db,
    "WayOfTheShortBlade_AdditionalAttackMarker": 0x5dc,
}


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board():
    from engine.entities.pathfinding.board import Board
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _triggered(aid: int) -> dict:
    """Une ligne d'`unitAbilityStates` : `raw[0]` = l'id d'ability, `raw[10]` = la HIERARCHIE
    (3 = TERTIAIRE, ce que lit `_load_tertiary_abilities`)."""
    raw = [0] * 12
    raw[0] = int(aid)
    raw[10] = 3
    return {"raw": raw, "level": NIVEAU_TERTIAIRE, "mult": MULT_TERTIAIRE}


def _charger(*, relique=True):
    unites, ab_units, snap_units, ob_units = [], [], [], []
    for i, (uid, vid, _rel, aid, _n) in enumerate(POSEUSES):
        unites.append({"id": uid, "visualId": vid, "alive": True, "team": 1, "owner": 1,
                       "pos": {"col": 1, "row": i}, "effects": []})
        snap_units.append({"entityId": uid, "visualId": vid, "entityType": 1,
                           "unitConfig": {"abilityVariablesMultiplier": MULT_PASSIF,
                                          "passiveAbilityLevel": NIVEAU_PASSIF,
                                          "activeAbilityLevel": NIVEAU_PASSIF}})
        ob_units.append({"squadId": uid, "hp": HP, "hpMax": HP})
        ab_units.append({"entityId": uid, "triggered": ([_triggered(aid)] if relique else [])})
    unites.append({"id": ENNEMI, "visualId": "orksNob", "alive": True, "team": 2, "owner": 2,
                   "pos": {"col": 6, "row": 6}, "effects": []})
    snap_units.append({"entityId": ENNEMI, "visualId": "orksNob", "entityType": 1})
    ob_units.append({"squadId": ENNEMI, "hp": HP, "hpMax": HP})
    return load_state({"currentPlayer": 1, "units": unites, "effects": []},
                      {"units": ob_units}, {"units": snap_units},
                      board=_board(), ability_states={"units": ab_units})


def _noms(state, uid):
    return sorted(e.name for e in (state.effects.by_unit.get(int(uid)) or ()))


# --------------------------------------------------------------------------------------------
# Etage 0 -- les ORDINAUX, figes au site
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("nom,ordinal", sorted(ORDINAUX_EFFET.items()))
def test_les_ordinaux_d_effet_sont_figes_au_site(nom, ordinal):
    assert int(EffectType[nom]) == ordinal, (
        "%s vaut %d, le decompile lisait 0x%x = %d" % (nom, int(EffectType[nom]), ordinal, ordinal))


@pytest.mark.parametrize("relic,aid", [(r, a) for _u, _v, r, a, _n in POSEUSES])
def test_les_ordinaux_d_ability_sont_figes_au_site(relic, aid):
    assert int(TriggeredAbilityType[relic]) == aid


def test_le_piege_1457_1458_est_reel_et_les_deux_espaces_nomment_AUTRE_CHOSE():
    """LE piege de ce lot, et il n'est pas theorique : `EffectType` 1457/1458 sont les DEUX effets
    de `RelicBoltPistol`, alors que `TriggeredAbilityType` 1457/1458 sont `KardiocoreGalvanus` et
    `PhoenixGem` -- les quatre vivent dans le MEME bloc de registre. Un appariement par l'ORDINAL
    y aurait ecrit deux entrees fausses sans lever la moindre erreur."""
    assert EffectType(1457).name == "RelicBoltPistol_ExtraPierce"
    assert EffectType(1458).name == "RelicBoltPistol_ExtraCritDamage"
    assert TriggeredAbilityType(1457).name == "KardiocoreGalvanus"
    assert TriggeredAbilityType(1458).name == "PhoenixGem"
    # Temoin de NON-DEGENERESCENCE : sans lui, ces quatre lignes passeraient sur des enums vides.
    assert EffectType(1457).name != TriggeredAbilityType(1457).name


# --------------------------------------------------------------------------------------------
# Etage 1 -- le REGISTRE : les sept POSEUSES y sont, les seize autres N'Y SONT PAS
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("relic,noms", [(r, n) for _u, _v, r, _a, n in POSEUSES])
def test_chaque_poseuse_a_son_entree_de_registre(relic, noms):
    assert tuple(F.get_owner_effects_added_on_ability_init(relic)) == tuple(noms)


@pytest.mark.parametrize("relic", sorted(NON_POSEUSES))
def test_aucune_non_poseuse_n_entre_au_registre(relic):
    """LE TEMOIN DE NON-DEGENERESCENCE DE L'ETAGE. Ces seize-la ont ete LUES et rendent NON ; les
    inscrire poserait des effets que le natif ne pose pas a l'init -- une sur-application
    SILENCIEUSE, exactement la faute symetrique de celle que le residu corrige."""
    assert F.get_owner_effects_added_on_ability_init(relic) == [], NON_POSEUSES[relic]


def test_le_passif_way_of_the_short_blade_entre_AUSSI():
    """Hors perimetre relique, meme lecture : c'est SA `CreateTrigger` qui porte le corps ICF
    partage de la forme (b), et son `CreateBehaviour` pose DEUX owner-effets sur `Owner`. Le
    canal AURA de 1499 (#1019-r1) etait INERTE hors capture live faute de cette entree."""
    assert F.get_owner_effects_added_on_ability_init("WayOfTheShortBlade") == [
        "WayOfTheShortBlade_DamageBuff", "WayOfTheShortBlade_AdditionalAttackMarker"]


# --------------------------------------------------------------------------------------------
# Etage 2 -- la POSE de bout en bout par `load_state`
# --------------------------------------------------------------------------------------------

def test_le_montage_ne_publie_AUCUN_owner_effet():
    """TEMOIN JOUE AVANT les assertions de pose : le montage ne met AUCUN effet dans
    `decisionView.effects`, donc tout ce que l'etage suivant observe vient du SEED et non du canal
    CAPTE. Sans ce temoin, un montage qui publierait les effets rendrait l'etage 2 vert a vide."""
    st = _charger(relique=False)
    for uid, _v, _r, _a, noms in POSEUSES:
        assert not (set(_noms(st, uid)) & set(noms)), _noms(st, uid)


@pytest.mark.parametrize("uid,vid,relic,aid,noms", POSEUSES)
def test_la_relique_equipee_POSE_ses_owner_effets(uid, vid, relic, aid, noms):
    st = _charger(relique=True)
    poses = _noms(st, uid)
    for n in noms:
        assert n in poses, "%s (%s) : %s absent de %s" % (relic, vid, n, poses)


@pytest.mark.parametrize("uid,vid,relic,aid,noms", POSEUSES)
def test_CONTRE_EPREUVE_sans_relique_aucun_owner_effet(uid, vid, relic, aid, noms):
    st = _charger(relique=False)
    poses = _noms(st, uid)
    for n in noms:
        assert n not in poses, "%s pose SANS relique equipee -- le gate a saute" % n


@pytest.mark.parametrize("uid,vid,relic,aid,noms", POSEUSES)
def test_CONTRE_EPREUVE_l_entree_de_registre_RETIREE_perd_la_pose(monkeypatch, uid, vid, relic,
                                                                  aid, noms):
    """Ce qui rattache la pose A CETTE ENTREE-LA, et pas a un autre chemin de seed."""
    monkeypatch.delitem(F.ABILITY_INIT_OWNER_EFFECTS, relic)
    poses = _noms(_charger(relique=True), uid)
    for n in noms:
        assert n not in poses, "%s pose encore SANS son entree -- le test ne mesure pas ce qu'il croit" % n


# --------------------------------------------------------------------------------------------
# Etage 3 -- la CONSEQUENCE : `PhoenixGem_CanRevive` arme un rail de trigger deja porte
# --------------------------------------------------------------------------------------------

def test_le_marqueur_de_phoenix_gem_arme_le_rail_des_triggers():
    """Cette entree-la n'est PAS cosmetique : tout le self-revive de #79 est branche sur
    `EFFECT_TRIGGERS[PhoenixGem_CanRevive]`. Sans la pose a l'init, le rail existait mais
    n'etait JAMAIS arme hors capture live."""
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    rail = EFFECT_TRIGGERS.get(int(EffectType.PhoenixGem_CanRevive)) \
        or EFFECT_TRIGGERS.get(EffectType.PhoenixGem_CanRevive)
    assert rail, "le rail EFFECT_TRIGGERS[1451] est vide -- l'entree n'aurait aucune consequence"
    uid = next(u for u, _v, r, _a, _n in POSEUSES if r == "PhoenixGem")
    assert "PhoenixGem_CanRevive" in _noms(_charger(relique=True), uid)
