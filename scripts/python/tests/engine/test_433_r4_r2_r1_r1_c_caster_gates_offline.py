"""OFFLINE #433-r4-r2-r1-r1-c -- les TROIS gates CASTER, gardes un par un.

Ce que ces tests gardent, et que le test LIVE ne peut pas garder : l'ORDRE des trois gates (le
live ne peut mesurer qu'un etat a la fois, donc il ne voit jamais LEQUEL des trois a mordu quand
plusieurs le pourraient), le TRI-ETAT du canal (« pas mesure » != « faux »), le mirror de
`StaticBattleRules.ActiveAbility$$IsDisabled` avec l'ordre de ses DEUX constantes, et la
non-contamination du cache de `unit_threat_reach`.

Chaine native : `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange` (surcharge a 4
arguments) -> slot 0x14 `AActiveAbility$$CanStillBeUsed`, slot 0x13 `AActiveAbility$$IsDisabled`,
puis `AttackQuery$$GetInvalidCasterReason` (dont la marche d lit
`ActiveAbility$$get_CanCurrentlyBeUsed`). Detail : `docs/rl/case-433-r4-r2-r1-r2-portees.md` §8.

ASCII only.
"""
from __future__ import annotations

import pytest

from engine.services import ability_caster_gates as acg
from engine.services import ability_range as ar

TERMINATOR = "darkaTerminator"        # arme de MELEE (1) + PlasmaCannon (1150) de zone 3
PLASMA = 1150
MARKSMAN = "tauMarksman"
SEEKER = 1069


def _st(**kw) -> dict:
    """Une ligne `decisionView.units[].abilities[]` -- les cinq champs de `readAbilityState`."""
    base = {"id": PLASMA, "kind": "active", "usable": True, "cooldown": None,
            "disabled": False, "ammoCost": None, "hasAmmo": True}
    base.update(kw)
    return base


# ------------------------------------------------------------------------------------------------
# GATE 2 -- `AActiveAbility$$IsDisabled` = `StaticBattleRules.ActiveAbility$$IsDisabled`
# ------------------------------------------------------------------------------------------------
def test_is_disabled_reads_nr_of_targets_first_then_nr_of_hits(monkeypatch):
    """L'ORDRE des deux constantes est la seule chose que ce gate contient, et il n'est PAS
    commutatif : `nrOfHits` n'est LU QUE si `nrOfTargets` est ABSENTE. Une ability portant
    `nrOfTargets = 2` et `nrOfHits = 0` n'est donc PAS disabled -- le natif a deja repondu."""
    table: dict = {}
    monkeypatch.setattr(acg, "try_get_number_constant",
                        lambda aid, key: table.get(key))
    monkeypatch.setattr(acg, "is_regular_attack", lambda aid: False)

    table.clear(); table.update({"nrOfTargets": 2, "nrOfHits": 0})
    assert acg.is_disabled(PLASMA) is False, "nrOfTargets present -> nrOfHits JAMAIS lu"

    table.clear(); table.update({"nrOfTargets": 0, "nrOfHits": 5})
    assert acg.is_disabled(PLASMA) is True

    table.clear(); table.update({"nrOfHits": 0})
    assert acg.is_disabled(PLASMA) is True, "nrOfTargets absente -> on tombe sur nrOfHits"

    table.clear()
    assert acg.is_disabled(PLASMA) is False, "les deux absentes -> le natif rend false"


def test_is_disabled_short_circuits_on_regular_attack(monkeypatch):
    """`if (IsRegularAttack(abilityType)) return false;` est la PREMIERE ligne : une attaque
    normale n'est jamais disabled, quelles que soient ses constantes."""
    monkeypatch.setattr(acg, "try_get_number_constant", lambda aid, key: 0)
    monkeypatch.setattr(acg, "is_regular_attack", lambda aid: True)
    assert acg.is_disabled(69) is False


def test_is_disabled_is_inert_on_the_whole_catalogue():
    """Le GISEMENT, mesure et non affirme : sur les 175 abilities ACTIVES distinctes du gameconfig,
    AUCUNE n'est disabled a ce build. Le gate est porte parce que le natif l'a ; ce test garde le
    fait qu'il ne retire rien aujourd'hui -- s'il se met a mordre, c'est une INFORMATION."""
    import gameconfig as GC
    ids = GC.all_unit_ids()
    names = set()
    for k in ("lineup", "npc", "summons"):
        for uid in (ids.get(k) or []):
            names.update((GC.unit(uid) or {}).get("activeAbilities") or [])
    assert len(names) >= 150, "catalogue anormalement petit : %d" % len(names)
    hits = sorted(n for n in names
                  if GC.ability_id(n) is not None and acg.is_disabled(GC.ability_id(n)))
    assert hits == [], "gisement de IsDisabled devenu non vide : %r" % (hits,)


def test_try_get_number_constant_is_a_tristate_on_real_gameconfig():
    """`TryGetNumberConstant` rend `false` quand la cle est ABSENTE -- le port rend `None`, jamais
    un zero invente. `PlasmaCannon` porte les deux cooldowns, pas `munitionsCost`."""
    assert acg.try_get_number_constant(PLASMA, acg.CONST_COOLDOWN_TURNS) == 1
    assert acg.try_get_number_constant(PLASMA, acg.CONST_INITIAL_COOLDOWN) == 1
    assert acg.try_get_number_constant(PLASMA, acg.CONST_MUNITIONS_COST) is None
    assert acg.try_get_number_constant(SEEKER, acg.CONST_COOLDOWN_TURNS) is None
    assert acg.try_get_number_constant(999999, acg.CONST_NR_OF_HITS) is None


# ------------------------------------------------------------------------------------------------
# GATE 3d -- `ActiveAbility$$get_CanCurrentlyBeUsed`, les QUATRE champs
# ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("state, expected", [
    (_st(), True),
    (_st(usable=False), False),
    (_st(disabled=True), False),
    (_st(cooldown=1), False),
    (_st(cooldown=0), True),                       # `RemainingCooldownTurns.Value < 1` -> pret
    (_st(ammoCost=2, hasAmmo=False), False),
    (_st(ammoCost=2, hasAmmo=True), True),
    (_st(ammoCost=None, hasAmmo=False), True),     # `!AmmoCost.HasValue` -> le terme est VRAI
])
def test_can_currently_be_used_truth_table(state, expected):
    """Mirror 1:1 de la propriete :

        if (!CanStillBeUsed || IsDisabled) return false;
        a = !RemainingCooldownTurns.HasValue || RemainingCooldownTurns.Value < 1;
        b = !AmmoCost.HasValue ? true : HasEnoughAmmo;
        return a && b;
    """
    assert acg.can_currently_be_used(state) is expected


def test_absent_channel_is_not_measured_not_false():
    """TRI-ETAT. Aucun canal -> `None` (« pas mesure »), et l'appelant ne gate PAS. Fabriquer un
    `False` ici retirerait TOUTES les abilities de toutes les zones ; fabriquer un `True`
    pretendrait avoir mesure."""
    assert acg.can_currently_be_used(None) is None
    assert acg.can_currently_be_used({}) is None
    assert acg.can_still_be_used(None) is None
    assert acg.gates_allow(PLASMA, None) is True
    assert acg.caster_gate_reason(PLASMA, None) is None


# ------------------------------------------------------------------------------------------------
# L'ORDRE des trois -- ce que le live ne peut pas voir
# ------------------------------------------------------------------------------------------------
def test_gate_order_can_still_be_used_wins_over_can_currently_be_used():
    """Gate 1 (slot 0x14) est evalue AVANT la marche d de `GetInvalidCasterReason`. Un etat qui
    rompt les DEUX doit etre impute au PREMIER."""
    assert acg.caster_gate_reason(PLASMA, _st(usable=False, cooldown=1)) \
        == acg.REASON_CAN_STILL_BE_USED


def test_gate_order_is_disabled_wins_over_can_currently_be_used(monkeypatch):
    """Gate 2 (slot 0x13) est evalue AVANT la marche d. Le gisement reel etant VIDE (cf.
    `test_is_disabled_is_inert_on_the_whole_catalogue`), l'ordre ne se garde qu'en forcant le
    gate -- c'est la seule facon d'atteindre le regime, pas un ajustement."""
    monkeypatch.setattr(acg, "is_disabled", lambda aid: True)
    assert acg.caster_gate_reason(PLASMA, _st(cooldown=1)) == acg.REASON_IS_DISABLED
    assert acg.caster_gate_reason(PLASMA, _st(usable=False)) == acg.REASON_CAN_STILL_BE_USED


def test_gate_reason_names_are_the_native_symbols():
    """Les trois etiquettes sont les noms des fonctions natives, pas des libelles libres : c'est ce
    qui rend le grep code <-> decompile immediat."""
    assert (acg.REASON_CAN_STILL_BE_USED, acg.REASON_IS_DISABLED,
            acg.REASON_CAN_CURRENTLY_BE_USED) == ("CanStillBeUsed", "IsDisabled",
                                                  "CanCurrentlyBeUsed")


# ------------------------------------------------------------------------------------------------
# Le canal `decisionView` -- la CLE est `id`, pas `abilityId`
# ------------------------------------------------------------------------------------------------
def test_ability_state_map_reads_the_id_key_emitted_by_projection():
    """`projectUnitsFull` emet `{id, name, kind, usable, cooldown, ...}` -- la cle est `id`. Lire
    `abilityId` (le nom qu'utilisent `abilityTargets`/`attackPlans`) rendrait une table VIDE, donc
    un port qui ne gate JAMAIS, silencieusement."""
    row = {"abilities": [{"id": 69, "kind": "normal"},
                         _st(id=PLASMA, cooldown=2),
                         {"kind": "active"}]}                 # ligne sans `id` -> ECARTEE
    m = acg.ability_state_map(row)
    assert sorted(m) == [69, PLASMA]
    assert m[PLASMA]["cooldown"] == 2
    assert acg.normal_attack_id(row) == 69
    assert acg.ability_state_map(None) == {}
    assert acg.normal_attack_id({"abilities": [{"id": 1, "kind": "active"}]}) is None


# ------------------------------------------------------------------------------------------------
# L'integration dans la ZONE -- `engine.services.ability_range`
# ------------------------------------------------------------------------------------------------
def test_reach_falls_to_the_weapon_when_the_gate_bites():
    """Le fait mesure LIVE, garde ici hors session : `darkaTerminator` porte a 3 par
    `PlasmaCannon`, et a 1 (son arme de MELEE) des que l'ability est annulee."""
    assert ar.unit_threat_reach(TERMINATOR) == 3
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: _st(cooldown=1)}) == 1
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: _st(cooldown=None)}) == 3
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: _st(usable=False)}) == 1
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: _st(disabled=True)}) == 1


def test_the_two_arms_are_separable_and_the_regime_is_not_degenerate():
    """ANTI-COINCIDENCE. Le kit est choisi pour que « zone = portee d'arme » soit FAUX quand
    l'ability est prete (3 != 1) : sans cela, un port qui gate TOUT passerait le bras bloque ET le
    temoin, et l'accord ne prouverait rien."""
    from engine.runner.abilities.targeting import unit_weapon_range
    assert unit_weapon_range(TERMINATOR, None) == 1
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: _st(cooldown=None)}) == 3
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: _st(cooldown=1)}) == 1


def test_absent_channel_keeps_the_status_quo():
    """BORNE nommee : sans canal, la zone est celle d'avant cette tranche (borne SUPERIEURE)."""
    assert ar.unit_threat_reach(TERMINATOR, None, None) == 3
    assert ar.unit_threat_reach(TERMINATOR, None, {}) == 3
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: {"id": PLASMA}}) == 3


def test_cache_is_not_contaminated_by_a_gated_call():
    """Le cache de `unit_threat_reach` est indexe par le seul `visual_id` : un appel PORTEUR d'etat
    ne doit ni le lire ni l'ecrire, sinon la premiere unite gatee figerait la valeur pour toutes
    les autres du meme kit."""
    ar._REACH_CACHE.pop(TERMINATOR, None)
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: _st(cooldown=1)}) == 1
    assert TERMINATOR not in ar._REACH_CACHE, "un appel etat-porteur a ecrit dans le cache"
    assert ar.unit_threat_reach(TERMINATOR) == 3
    assert ar.unit_threat_reach(TERMINATOR, None, {PLASMA: _st(cooldown=1)}) == 1


def test_the_normal_attack_passes_the_same_gates():
    """La lambda `AttackQuery.u003Cu003Ec__DisplayClass39_1$$u003CGetAllTilesInAbilityRangeu003Eb__0`
    enumere l'`ActiveAbilityComponent` ENTIER ; `includeNormalAttack` ne fait que LEVER le filtre
    `!IsRegularAttack`. L'entree de l'attaque normale passe donc par les trois memes gates -- le
    port ne la traite pas a part des que son id est publie."""
    st = {69: {"id": 69, "kind": "normal", "usable": False},
          PLASMA: _st(cooldown=1)}
    assert ar.unit_threat_reach(TERMINATOR, None, st, 69) == 0
    assert ar.is_tile_in_range_of_any_ability((0, 0), (1, 0), TERMINATOR,
                                              ability_state=st, normal_attack_id=69) is False
    # meme etat, mais l'id de l'attaque normale non publie -> le terme d'arme SURVIT (borne sup.)
    assert ar.is_tile_in_range_of_any_ability((0, 0), (1, 0), TERMINATOR,
                                              ability_state=st) is True


@pytest.mark.parametrize("cooldown, expected", [(1, [True, False, False]),
                                                (None, [True, True, True])])
def test_tile_partition_matches_the_two_arms(cooldown, expected):
    """La partition PAR DISTANCE des deux bras, hors session : `d = 1, 2, 3` depuis l'ennemi."""
    st = {PLASMA: _st(cooldown=cooldown)}
    got = [ar.is_tile_in_range_of_any_ability((0, 0), (d, 0), TERMINATOR, ability_state=st)
           for d in (1, 2, 3)]
    assert got == expected


def test_marksman_is_unchanged_when_its_ability_is_ready():
    """NON-REGRESSION de la tranche precedente : le kit qui l'avait mesuree garde sa zone de 5 des
    lors que son ability n'est pas gatee -- avec canal comme sans."""
    ready = {SEEKER: _st(id=SEEKER)}
    assert ar.unit_threat_reach(MARKSMAN) == 5
    assert ar.unit_threat_reach(MARKSMAN, None, ready) == 5
    assert ar.unit_threat_reach(MARKSMAN, None, {SEEKER: _st(id=SEEKER, usable=False)}) == 3
