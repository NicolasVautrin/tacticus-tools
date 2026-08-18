"""#967-r4 -- CLIQUET : le SECOND disjoint du bonus de 500 de `1214 Hailstrike`.

`IdunBattleLogic.AI.Playbook.Loki.HailstrikePlaybook$$GetTargetUtility` :

    if (UnitExtensions$$HasTrait(target, UnitTrait.Overwatch)) bonus = 500;
    else if (   (UnitExtensions$$HasRangedWeapon(target)
              || UnitExtensions$$HasRangedAbility(target, query))
             && query.<slot 56 = CanAttackAnyUnitFromAnyTileWithAnyAbility>(target)) bonus = 500;

Le port ne mirroirait que le PREMIER disjoint. Le second, LU sur `t6dpr4k06g` :

    IdunBattle.Entities.UnitExtensions$$HasRangedAbility(unit, query) :
        foreach (ability in unit.GetComponent<ActiveAbilities>().<+0x20>)
            if (query.<slot 6>(Nullable<AbilityOrEffect>(ability)) == AttackRangeType.Ranged)
                return true;
        return false;

Le slot **6** d'`IBattleQuery` est `GetAbilityAttackRangeType`/1 (LU dans
`data/symbols/<build>/metadata/interface_slots.tsv` ; ses freres d'arite 4 sont les slots 2/3/4).
Le predicat est donc, mot pour mot, `attack_range_type(<nom>) == "Ranged"`.

DIRECTION DE L'ECART REPARE : **RESTRICTIVE**. Une cible sans arme a distance mais dotee d'une
ability a distance perdait son bonus de 500, donc le port pouvait buffer un AUTRE allie que le
natif. Le bonus DOMINE le terme de percage (500 contre au plus 100), donc l'ecart changeait la
CIBLE, pas seulement le score.

REGIME, re-derive du gameconfig du build (etage 0, assertionne NON VIDE) : **29** unites portent
une active `Ranged` SANS arme a `Range`. Deux sont des DarkAngels, donc des allies naturels du
porteur : `darkaTerminator` (`PlasmaCannon`) et `darkaStormSpeeder` lui-meme (`Hailstrike`).

CONTRE-EPREUVE : l'etage 2 rejoue le regime d'AVANT (premier disjoint SEUL) et doit DIVERGER sur
exactement ces unites-la. L'etage 3 substitue l'etage `attack_range_type` et verifie que la
substitution MORD avant d'en tirer une conclusion.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PYDIR = Path(__file__).resolve().parents[3]                  # scripts/python
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType            # noqa: E402
from engine.playbook import noncomparable as NC                              # noqa: E402
from engine.services import battle_query as SBQ                              # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/noncomparable/storm_speeder.py",
                "scripts/python/engine/services/battle_query.py"),
    "build": True,
    "toujours": False,
    "raison": "Deux foyers : le playbook qui porte le disjoint, et l'etage "
              "`attack_range_type` (mirror du slot 6) dont il depend entierement. "
              "`build: True` : le regime et les temoins sont re-derives du gameconfig du build, "
              "et une bascule d'`attackRangeType` doit faire rougir ce fichier.",
}

HAILSTRIKE = int(ActiveAbilityType.Hailstrike)               # 0x4be = 1214
PB = NC.PLAYBOOKS[HAILSTRIKE]

#: Temoins NOMMES, tous re-verifies par l'etage 0 -- jamais recopies a l'aveugle.
T_ABILITY_SEULE = "darkaTerminator"          # active `PlasmaCannon` = Ranged, AUCUNE arme Range
T_MELEE_SEULE = "custoBladeChampion"         # active `MartialInspiration` = Melee
T_SANS_ACTIVE = "darkaSmnWatcher"            # aucune active du tout


def _ctx():
    """`NCContext` reduit : `_ranged_bonus` ne lit que `ctx.plans`. `{}` = plans NON publies,
    donc le conjoint slot 56 est NON MESURE et le port retient le seul disjoint -- exactement le
    regime que la docstring du playbook decrit."""
    return SimpleNamespace(plans={}, debug=False, uid=1)


def _regime() -> dict:
    """`{unitId: [actives Ranged]}` pour les unites SANS arme a `Range`. Re-derive, jamais cite."""
    idx = GC._index()
    out = {}
    for source in ("lineup", "npc", "summons"):
        for uid, cfg in (idx.get(source) or {}).items():
            if any((w or {}).get("Range") for w in (cfg.get("weapons") or [])):
                continue
            ranged = [n for n in (cfg.get("activeAbilities") or [])
                      if SBQ.attack_range_type(n) == "Ranged"]
            if ranged:
                out[uid] = ranged
    return out


REGIME = _regime()


# --------------------------------------------------------------------------------------------
# ETAGE 0 -- le regime EXISTE, et les temoins sont ce que ce fichier croit qu'ils sont.
# --------------------------------------------------------------------------------------------
def test_etage0_le_regime_du_fix_est_non_vide():
    assert REGIME, (
        "aucune unite du build n'a d'active `Ranged` sans arme a `Range` : ce fichier "
        "n'exercerait RIEN et passerait pour vert")
    assert len(REGIME) >= 10, (
        "le gisement s'est effondre (%d) -- re-deriver avant de conclure" % len(REGIME))
    assert T_ABILITY_SEULE in REGIME, (
        "`%s` n'est plus dans le regime : le temoin de l'etage 2 est PERIME" % T_ABILITY_SEULE)


@pytest.mark.parametrize("uid,attendu_ranged,attendu_arme", [
    (T_ABILITY_SEULE, True, False),
    (T_MELEE_SEULE, False, False),
    (T_SANS_ACTIVE, False, False),
])
def test_etage0bis_les_temoins_sont_ce_qu_on_croit(uid, attendu_ranged, attendu_arme):
    cfg = GC.unit(uid) or {}
    assert cfg, "unite `%s` absente du gameconfig du build" % uid
    arme = any((w or {}).get("Range") for w in (cfg.get("weapons") or []))
    ranged = any(SBQ.attack_range_type(n) == "Ranged"
                 for n in (cfg.get("activeAbilities") or []))
    assert (ranged, arme) == (attendu_ranged, attendu_arme), (
        "le temoin `%s` a change de profil : (active Ranged, arme Range) = (%s, %s)"
        % (uid, ranged, arme))


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- le mirror de `HasRangedAbility` lui-meme.
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("uid,attendu", [(T_ABILITY_SEULE, True),
                                         (T_MELEE_SEULE, False),
                                         (T_SANS_ACTIVE, False)])
def test_etage1_has_ranged_ability(uid, attendu):
    assert PB._has_ranged_ability(GC.unit(uid) or {}) is attendu


def test_etage1bis_une_config_vide_rend_faux_sans_lever():
    """`GetComponent` absent -> le natif leve ; le port ne mirroir pas une levee et rend `False`,
    la degradation etant du cote RESTRICTIF (le statu quo)."""
    assert PB._has_ranged_ability({}) is False
    assert PB._has_ranged_ability({"activeAbilities": []}) is False


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- LE BONUS, et la CONTRE-EPREUVE : le regime d'AVANT diverge exactement sur `REGIME`.
# --------------------------------------------------------------------------------------------
def _bonus_avant_le_fix(uid: str) -> float:
    """L'ecriture d'AVANT #967-r4 : PREMIER disjoint seul, plans non publies."""
    cfg = GC.unit(uid) or {}
    if PB.TRAIT_OVERWATCH.name in (cfg.get("traits") or []):
        return PB.RANGED_BONUS
    if not any((w or {}).get("Range") for w in (cfg.get("weapons") or [])):
        return 0.0
    return PB.RANGED_BONUS


def test_etage2_le_bonus_est_accorde_a_la_cible_a_ability_a_distance():
    assert PB._ranged_bonus(_ctx(), 1, T_ABILITY_SEULE) == PB.RANGED_BONUS
    assert _bonus_avant_le_fix(T_ABILITY_SEULE) == 0.0, (
        "CONTRE-EPREUVE MUETTE : le regime d'AVANT accordait deja le bonus, ce test ne mesure rien")


def test_etage2bis_le_bonus_reste_refuse_a_qui_n_a_ni_arme_ni_ability_a_distance():
    for uid in (T_MELEE_SEULE, T_SANS_ACTIVE):
        assert PB._ranged_bonus(_ctx(), 1, uid) == 0.0, (
            "le fix a ouvert une passoire sur `%s`" % uid)


def test_etage2ter_la_divergence_est_EXACTEMENT_le_regime_mesure():
    """Ni plus (une passoire), ni moins (un fix inerte) : sur les unites SANS trait Overwatch, le
    fix ne change le bonus que pour celles qui ont une active `Ranged` et pas d'arme a `Range`."""
    idx = GC._index()
    diverge, total = set(), 0
    for source in ("lineup", "npc", "summons"):
        for uid, cfg in (idx.get(source) or {}).items():
            if PB.TRAIT_OVERWATCH.name in (cfg.get("traits") or []):
                continue                       # le trait court-circuite les deux disjoints
            total += 1
            if PB._ranged_bonus(_ctx(), 1, uid) != _bonus_avant_le_fix(uid):
                diverge.add(uid)
    attendu = {u for u in REGIME
               if PB.TRAIT_OVERWATCH.name not in ((GC.unit(u) or {}).get("traits") or [])}
    assert total > 100, "balayage degenere (%d unites visitees)" % total
    assert diverge == attendu, (
        "divergence inattendue -- en trop : %s ; manquantes : %s"
        % (sorted(diverge - attendu), sorted(attendu - diverge)))


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- le disjoint passe bien par l'ETAGE `attack_range_type` (slot 6), et pas par un
# critere reinvente. La substitution porte son controle de morsure.
# --------------------------------------------------------------------------------------------
def test_etage3_le_disjoint_lit_le_slot_6_et_rien_d_autre(monkeypatch):
    cfg = GC.unit(T_MELEE_SEULE) or {}
    assert PB._has_ranged_ability(cfg) is False
    monkeypatch.setattr(SBQ, "attack_range_type", lambda _n: "Ranged")
    assert PB._has_ranged_ability(cfg) is True, (
        "la substitution d'`attack_range_type` NE MORD PAS : le disjoint lit autre chose que le "
        "slot 6, et les etages precedents ne prouvent pas ce qu'ils annoncent")
    monkeypatch.setattr(SBQ, "attack_range_type", lambda _n: "Melee")
    assert PB._has_ranged_ability(GC.unit(T_ABILITY_SEULE) or {}) is False


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- l'ATTAQUE NORMALE vit dans le MEME composant natif, et elle est NEUTRE. Mesure.
# --------------------------------------------------------------------------------------------
def test_etage4_les_ids_d_attaque_normale_sont_neutres():
    """`UnitFactory$$AddNormalAttackAbility` pousse l'attaque normale dans le composant que
    `HasRangedAbility` itere. Ne pas l'enumerer offline ne change aucun verdict PARCE QUE ses ids
    n'ont aucune entree gameconfig -- donc `GetAbilityAttackRangeType` y rend `None`."""
    noms = [m.name for m in ActiveAbilityType
            if "NormalAttack" in m.name or m.name.startswith("Attack")]
    assert noms, "aucun id d'attaque normale reconnu : la mesure serait vide"
    sans_entree = [n for n in noms if GC.ability(n) is None]
    assert sans_entree == noms, (
        "des ids d'attaque normale ont desormais une entree gameconfig (%s) : leur "
        "`attackRangeType` doit etre relu avant de les declarer neutres"
        % sorted(set(noms) - set(sans_entree)))
    assert PB._has_ranged_ability({"activeAbilities": noms}) is False


# --------------------------------------------------------------------------------------------
# ETAGE 5 -- NON-REGRESSION : le trait `Overwatch` court-circuite toujours les deux disjoints.
# --------------------------------------------------------------------------------------------
def test_etage5_overwatch_domine_toujours():
    idx = GC._index()
    porteurs = [u for src in ("lineup", "npc", "summons")
                for u, c in (idx.get(src) or {}).items()
                if PB.TRAIT_OVERWATCH.name in ((c or {}).get("traits") or [])]
    assert porteurs, "aucun porteur du trait Overwatch : l'etage 5 serait vide"
    for uid in porteurs:
        assert PB._ranged_bonus(_ctx(), 1, uid) == PB.RANGED_BONUS
