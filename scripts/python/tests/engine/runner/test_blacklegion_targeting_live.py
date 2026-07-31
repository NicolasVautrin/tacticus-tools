"""#250 -- GARDE des masques de ciblage du module `blacklegion` (1021, 1022, 1036, 1147, 1148).

Les cinq entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` : `get_invalid_target_reason`
rendait 0 des sa premiere ligne, donc AUCUN gate -- le moteur acceptait des casts que
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. Degradation PERMISSIVE, ni
erreur ni crash : invisible en self-play, et exactement l'espace qu'un entrainement RL irait
exploiter.

LES TROIS FORMES DE CTOR SONT TOUTES REPRESENTEES ICI, ET C'EST LE POINT :

  * 1021 `IncursionAbility$$.ctor` et 1147/1148 -> **FLAGS DIRECTS** (`TargetingOptions..ctor(&opts,
    isSelfCasting, &range, forceMeleeTarget, <rules>, 0, 0, 0)`) : le litteral EST le masque ;
  * 1022 `BringerOfDespairAbility$$.ctor` et 1036 `FrenziedFiringAbility$$.ctor` -> **PRESET
    STATIQUE COPIE** : aucun `TargetingOptions..ctor` appele, le masque est la constante ecrite par
    `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`.

Et les deux pieges du module y sont exerces :
  * 1022 recopie le MEME preset `statics+0x40` que 1020 `HeraldOfTheApocalypse`, 1122 `CordClaw` et
    1029 `Drachnyen` -- quatre porteurs, MEME masque `0x4000`. (Le commentaire disait auparavant que
    1029 y ajoutait `0x200000000` via la surcharge PRESET + flags : REFUTE par les xrefs entrantes
    des trois surcharges de `TargetingOptions..ctor` -- 1029 appelle la surcharge 2 arguments, la
    copie PURE. Cf. `docs/rl/case-302-4-population-cible-tuile.md` §5.3.)
  * 1036 recopie le preset `statics+0x140`, qui ne differe de celui de 1104 `SpiritLeech` (+0x180)
    QUE par `forceMeleeTarget` (`RangedBool.True` contre `RangedBool.False`). C'est le champ le plus
    facile a recopier au voisin, et celui qui change le REGIME de portee au contact : les tests 1021
    et 1036 rejouent donc DEUX geometries -- `far` (aucun ennemi au contact du caster : discrimine la
    valeur de portee) et `near` (un ennemi au contact : discrimine `forceMeleeTarget`, qui n'est
    LISIBLE que la).

Le montage (geometrie CONDUITE sur un runner `--no-ai`, les deux camps pilotes) et les lectures
natif/port vivent dans `scripts/python/probe_250_blacklegion_targeting.py::measure` -- le probe
MESURE, ce test GARDE, une seule implementation. Lit l'etat LIVE, aucune RVA ni tuile hardcodee,
ASCII only.
"""
from __future__ import annotations

import probe_250_blacklegion_targeting as P
from engine.runner.abilities.targeting_rule import TargetingRule as TR


def _show(out, aid: int) -> None:
    print("\n[%d targeting] caster=u%d board=%s seed=%s geom=%s abilityState=%s"
          % (aid, out["caster"], out["board"], out["seed"], out["geom"], out["abilityState"]))
    for r in out["rows"]:
        print("  %-28s id=%-4d d=%-3s natif=%-12s caster=%-5s %s"
              % (r["label"], r["targetId"], r["dist"],
                 "-" if r["nat"] is None else hex(r["nat"]),
                 "-" if r["nat_caster"] is None else hex(r["nat_caster"]),
                 " ".join("%s=%s" % (v, hex(r[v])) for v in out["variants"])))


def _check(out, aid: int):
    """Les quatre garde-fous COMMUNS, plus les attendus de contrefactuel declares dans `SPECS`.

    L'ordre compte : la garde 0 d'abord (sans une seule cible ACCEPTEE, les refus mesures peuvent
    venir du court-circuit `ActiveAbility.CanCurrentlyBeUsed` d'`AttackQuery$$GetInvalidTargetReason`
    et ne prouvent rien) ; l'accord natif/port ensuite -- c'est CETTE assertion qui tombe quand
    `TARGETING_OPTIONS` disparait."""
    rows, spec = out["rows"], P.SPECS[aid]
    _show(out, aid)

    assert any(r["nat"] == 0 for r in rows), (
        "aucune cible ACCEPTEE par le natif -> l'ability est peut-etre court-circuitee "
        "(`CanCurrentlyBeUsed`) et les refus mesures ne prouvent rien")

    desaccords = [(r["label"], hex(r["nat"] or 0), hex(r["apres"])) for r in rows
                  if r["nat"] != r["apres"]]
    assert not desaccords, "desaccord natif/port sur %s : %s" % (spec["name"], desaccords)

    gains = [r["label"] for r in rows if r["nat"] not in (None, 0) and r["avant"] == 0]
    assert gains, ("aucune ligne ou le masque change le verdict -> ce test ne garderait rien "
                   "(il passerait aussi sans `TARGETING_OPTIONS`)")

    for v, (_transform, attendu) in sorted(spec["variants"].items()):
        n = sum(1 for r in rows if r["nat"] != r[v])
        if attendu[out["geom"]] == "discriminant":
            assert n > 0, ("contrefactuel `%s` (geometrie %s) ne change AUCUN verdict -> le champ "
                           "n'est pas verrouille par ce montage" % (v, out["geom"]))
        else:
            assert n == 0, ("contrefactuel `%s` (geometrie %s) devait etre INERTE et change %d "
                            "verdict(s) -> relire le preset / le regime de portee"
                            % (v, out["geom"], n))
    return rows


def _row_at(rows, dist: int, side: str = "ENNEMI"):
    return next((r for r in rows if r["dist"] == dist and r["label"].startswith(side)), None)


# ------------------------------------------------------------------------------------------------
# 1021 Incursion -- FLAGS DIRECTS, 0x4020, RANGE_FROM_CONFIG(2), forceMeleeTarget=IfRangedCaster
# ------------------------------------------------------------------------------------------------

def test_incursion_targeting_mask_matches_native(host, live_session):
    """`blackPossession` PORTE une arme a `Range` 2 -> `RangedBool.IfRangedCaster` est VRAI, donc le
    clamp melee de `TargetingQuery$$GetRange` MORD des qu'un ennemi est au contact. Les deux
    geometries encadrent les deux regimes : portee 2 sans contact, adjacence avec."""
    far = _check(P.measure(live_session, 1021, "far", "MC1_67", "777"), 1021)
    # SANS ennemi au contact : la portee de config (2) est LISIBLE et encadree des DEUX cotes.
    assert (_row_at(far, 2) or {}).get("nat") == 0, \
        "ennemi a d=2 non accepte -> `RANGE_FROM_CONFIG` (constants.range = 2) n'est pas encadre"
    assert (_row_at(far, 3) or {}).get("nat") == int(TR.TargetIsInRange), \
        "ennemi a d=3 non refuse -> la portee n'est pas encadree par le haut"

    near = _check(P.measure(live_session, 1021, "near", "C4_09", "31337"), 1021)
    # AVEC un ennemi au contact : `ShouldApplyRangedInMelee` -> `Math.Min(1, v)` + `onlyAdjacent`,
    # la MEME cible a d=2 devient illegale. C'est la SEULE lecture qui prouve `forceMeleeTarget`.
    assert (_row_at(near, 1) or {}).get("nat") == 0, "ennemi au contact non accepte"
    assert (_row_at(near, 2) or {}).get("nat") == int(TR.TargetIsInRange), (
        "ennemi a d=2 non refuse alors qu'un ennemi est au contact -> le clamp melee "
        "(`forceMeleeTarget = IfRangedCaster`) n'est pas exerce")
    assert any(r["nat"] == int(TR.TargetIsEnemy) for r in near), \
        "aucun refus TargetIsEnemy -> le volet CAMP n'est pas exerce"


# ------------------------------------------------------------------------------------------------
# 1022 BringerOfDespair -- PRESET +0x40 COPIE, 0x4000, RANGE_ADJACENT, forceMeleeTarget=False
# ------------------------------------------------------------------------------------------------

def test_bringer_of_despair_targeting_mask_matches_native(host, live_session):
    """Masque NU (le preset `statics+0x40` sans aucun flag OR'e) : `TargetIsEnemy` seul, portee =
    ADJACENCE. Le cas limite n'est donc pas une portee numerique mais **d=2**, la premiere distance
    hors contact -- et le contrefactuel `rangeDist2` (meme portee numerique, sans `onlyAdjacent`)
    est ce qui verrouille le REGIME plutot qu'« une portee »."""
    rows = _check(P.measure(live_session, 1022, "far", "MC1_67", "777"), 1022)
    assert (_row_at(rows, 1) or {}).get("nat") == 0, "ennemi au contact non accepte"
    assert (_row_at(rows, 2) or {}).get("nat") == int(TR.TargetIsInRange), \
        "ennemi a d=2 non refuse -> l'adjacence n'est pas encadree par le haut"
    assert any(r["nat"] == int(TR.TargetIsEnemy) for r in rows), \
        "aucun refus TargetIsEnemy -> le volet CAMP n'est pas exerce"
    # Le masque NU ne porte AUCUN bit du volet CASTER. 1029 Drachnyen recopie LE MEME preset et a
    # donc le MEME masque (`0x4000`) -- la separation supposee entre les deux etait un artefact du
    # commentaire, pas du natif (cf. `case-302-4` §5.3).
    assert all(r["nat_caster"] == 0 for r in rows), \
        "casterReason natif non nul -> une regle du volet caster mord et n'est pas portee"


# ------------------------------------------------------------------------------------------------
# 1036 FrenziedFiring -- PRESET +0x140 COPIE, 0x4002, RANGE_FROM_CONFIG(3), forceMelee=True
# ------------------------------------------------------------------------------------------------

def test_frenzied_firing_targeting_mask_matches_native(host, live_session):
    """Le preset `+0x140` pose `forceMeleeTarget = 0 = RangedBool.True` -- c'est le SEUL champ par
    lequel il differe du preset `+0x180` de 1104 `SpiritLeech`, et il change tout au contact :
    Volk porte a 3 en terrain degage, a 1 des qu'un ennemi le touche."""
    far = _check(P.measure(live_session, 1036, "far", "MC1_67", "777"), 1036)
    assert (_row_at(far, 3) or {}).get("nat") == 0, \
        "ennemi a d=3 non accepte -> `RANGE_FROM_CONFIG` (constants.range = 3) n'est pas encadre"
    assert (_row_at(far, 5) or {}).get("nat") == int(TR.TargetIsInRange), \
        "ennemi a d=5 non refuse -> la portee n'est pas encadree par le haut"

    near = _check(P.measure(live_session, 1036, "near", "C4_09", "31337"), 1036)
    assert (_row_at(near, 1) or {}).get("nat") == 0, "ennemi au contact non accepte"
    assert (_row_at(near, 3) or {}).get("nat") == int(TR.TargetIsInRange), (
        "ennemi a d=3 non refuse alors qu'un ennemi est au contact -> le clamp melee "
        "(`forceMeleeTarget = RangedBool.True`) n'est pas exerce ; c'est EXACTEMENT ce qu'on "
        "obtiendrait en recopiant le preset de 1104 SpiritLeech")


# ------------------------------------------------------------------------------------------------
# 1147 / 1148 -- MACHINE OF WAR `blackForgefiend`, FLAGS DIRECTS, RANGE_WHOLE_BOARD
# ------------------------------------------------------------------------------------------------

def test_hades_autocannons_targeting_mask_matches_native(host, live_session):
    """1147 vise un SUMMON ENNEMI, et rien d'autre. Le montage AMENE la cible : le `blackPossession`
    ADVERSE caste `Incursion` (1021), ses `blackSmnBloodletter` apparaissent DANS SON CAMP -- donc
    des summons ENNEMIS pour la MoW.

    ⚠ GARDE D'ORACLE. La surcharge 4 arguments d'`AttackQuery$$GetInvalidTargetReason` court-circuite
    sur `ActiveAbilityComponent.GetOrNull(...) == null` / `!ActiveAbility.CanCurrentlyBeUsed` et rend
    alors le litteral `1` SANS traverser la cascade -- un `0x1` ne dirait RIEN du masque. Deux
    conditions rendent l'oracle valide pour un caster MoW, et le montage les tient : (a) le seed BC
    est patche (`MachineOfWarAmmo`, cf. `probe_250.seed_bc_with_ammo`) sans quoi `CanCurrentlyBeUsed`
    est faux ; (b) le `casterId` est celui de `decisionView.mows[].casterId`, pas
    `observeBattle.mows[].id`. Le test le VERIFIE en confrontant un SECOND oracle natif,
    `abilityTargets.fromHere` (chemin `AttackQuery$$GetValidTargets`), a l'ensemble des cibles que
    `abilityReason` accepte."""
    out = P.measure(live_session, 1147, "far", "MC1_67", "777")
    rows = _check(out, 1147)

    summons = [r for r in rows if "Bloodletter" in r["label"]]
    assert summons, ("aucun summon ennemi monte -> `TargetIsSummon` n'a aucune cible ACCEPTABLE et "
                     "le masque n'est pas encadre par le haut")
    assert all(r["nat"] == 0 for r in summons), \
        "un summon ennemi refuse par le natif -> le montage n'est pas celui qu'on croit"
    assert any(r["nat"] == int(TR.TargetIsSummon) for r in rows), \
        "aucun refus TargetIsSummon -> la regle-cle de 1147 n'est pas exercee"
    assert any(r["nat"] == int(TR.TargetIsEnemy) for r in rows), \
        "aucun refus TargetIsEnemy -> le volet CAMP n'est pas exerce"

    accepted = {r["targetId"] for r in rows if r["nat"] == 0}
    assert set(out["native_valid_targets"]) & {r["targetId"] for r in rows} == accepted, (
        "les deux oracles NATIFS divergent (`abilityTargets.fromHere` vs `abilityReason == 0`) -> "
        "le court-circuit `CanCurrentlyBeUsed` a probablement mordu, la mesure ne prouve rien")


def test_daemonic_ordnance_targeting_mask_matches_native(host, live_session):
    """1148 vise une TUILE, et n'a AUCUNE regle de camp : le seul refus possible est
    `TargetIsTile` sur une tuile NON MARCHABLE (`AllowUnwalkableTargetTile` absent), et le natif y
    rend le LITTERAL `1` = `TargetingRule.ValidRequest` -- une valeur qu'on ne peut pas exclure du
    contrat sous pretexte qu'elle signifie ailleurs « ability indisponible ».

    Deux abilities du MEME porteur, deux masques sans rapport : ne jamais lire un masque « par
    porteur »."""
    rows = _check(P.measure(live_session, 1148, "far", "MC1_67", "777"), 1148)
    unwalk = [r for r in rows if r["label"].startswith("TUILE non-marchable")]
    walk = [r for r in rows if r["label"].startswith("TUILE marchable")]
    assert unwalk and walk, "le board ne fournit pas les deux cotes du predicat de marchabilite"
    assert all(r["nat"] == int(TR.ValidRequest) for r in unwalk), (
        "tuile NON marchable non refusee -> `TargetIsTile` n'est pas exerce (et c'est bien le "
        "litteral 1 `ValidRequest` que le natif rend ici)")
    assert all(r["nat"] == 0 for r in walk), "tuile marchable refusee -> le predicat est inverse"
    # AUCUNE regle de camp : allies ET ennemis sont des cibles legales. Ne pas inventer un refus.
    assert all(r["nat"] == 0 for r in rows if r["label"].startswith(("ALLIE", "ENNEMI"))), \
        "une unite refusee alors que 1148 ne porte NI TargetIsEnemy NI TargetIsFriendly"
