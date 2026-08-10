"""#419-r1 tranche 11 -- le terme `SpecialIssueCombiMelta_LikesRange3` (+25) du `pairUtility`,
confronte au NATIF sur son porteur REEL, **et desormais dans la CONFIGURATION REELLE DU JEU**.

`IdunBattle.AI.Playbook.Loki.SpecialIssueCombiMeltaPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
verse le poids quand `IBattleQuery.<slot 0x6c = GetDistance>(case.Target, case.CasterPosition.MainTile)`
vaut EXACTEMENT 3, et ne fait AUCUN yield sinon. Il entre dans la face ATTACK du dispatcher
`TriggeredAbilitiesUtility(2)`, donc DANS le terme de paire -- directement confrontable a l'oracle
natif `pairUtility`.

## LE BRAS `neutered` A DISPARU (#419-r1-tr11-r3), ET C'EST LE PORT QUI L'A TUE
Ce fichier montait DEUX bras. Le second (`neutered`) forcait a 0, dans le seed BC, les variables de
degat de l'ability, pour que la face COMBAT non portee cesse de perturber la prediction -- un patch
INVISIBLE DU PORT (motif `#366-r1-bcpatch-invisible`), licite tant que le port ne modelisait pas ces
variables. Il declarait lui-meme sa condition de validite, et un garde OFFLINE derive du registre la
tenait : *« des que la face COMBAT entre au registre, le meme geste devient une DESYNCHRONISATION »*.

La face COMBAT est portee (effets **1563** `SpecialIssueCombiMelta_AdditionalHits` a `d == 2` et
**1564** `_ExtraDmg` a `d == 1`, cf. `entities/effects/loki/hits.py` et `.../extra_damage.py`). Le
garde a donc fait ce pour quoi il etait ecrit, et la reponse est celle qu'il prescrivait : **retomber
sur le seul bras `raw`** -- qui n'a plus besoin d'etre borne a la distance 3, puisque le port colle
maintenant au natif aux TROIS distances. Les trois entrees `SpecialIssueCombiMelta` de
`probe_366_r1_bcpatch_port_blindspot._EXCEPTIONS` sont retirees dans le meme commit.

CE QUE CE FICHIER GARDE :

  1. **CONFORMITE, aux TROIS distances, SANS AUCUN PATCH ET SANS AUCUNE EXEMPTION** -- l'utilite de
     paire du port egale celle du natif, tuile par tuile et cible par cible, a 1e-4 pres, sur
     TOUTES les lignes. Le predicat d'exemption `_is_residual` a DISPARU : le regime residuel
     `#419-r1-tr11-r5` est FERME (cf. (5)).
  2. **DISCRIMINANCE** -- le meme moteur, playbook 1545 RETIRE du registre, DOIT diverger du natif
     d'EXACTEMENT le poids BC sur les tuiles a distance 3, et de RIEN aux distances 1 et 2. Sans
     cette seconde assertion, un port qui ignore le terme passerait.
  3. **LA CIBLE LUE EST `case.Target`** -- depuis une meme tuile, les DEUX cibles (placees
     adjacentes) sont a des distances differentes, et une seule recoit le poids.
  4. **LA FACE COMBAT EST AU REGISTRE** -- garde derive, pendant EXACT de l'ancien garde de
     condition de validite : si elle en sortait, ce fichier redeviendrait un montage a deux bras.
  5. **LE BI-CANAL ROLL/DISPLAY EST MODELISE, ET LE MONTAGE LE DISCRIMINE** (`#419-r1-tr11-r5`,
     FERME). Le garde precedent exigeait qu'AU MOINS UNE ligne diverge, et il a rougi comme il
     etait ecrit pour le faire : il prescrivait alors de retirer l'exemption de (1), de le
     supprimer et de fermer le residu -- c'est fait. A sa place, un garde OFFLINE qui empeche le
     vert de (1) d'etre VIDE : le descripteur 1563 doit publier les DEUX canaux (`amount` =
     `Fix64.Round((min+max)/2)` demi-vers-le-PAIR pour la PREDICTION, `min`/`max` pour le COMBAT)
     ET les deux modeles doivent etre SEPARABLES sur ce montage (`max != 1.5 x min`, la seule
     configuration ou `avg +/- 20 %` et `[min, max]` coincident).
  6. **CHAQUE LECTURE A UN REGIME OU SON MUTANT MORD** -- six contre-epreuves, chacune avec sa
     RECIPROQUE (au moins une ligne ou elle ne mord pas).

Le montage EXIGE l'injection catalogue du porteur, l'ability 1545 a son `AbilitiesComponent`, les
trois distances et un poids BC non nul ; s'il ne les obtient pas il ECHOUE, il ne skippe pas
(#268 -- un skip sur un regime non atteint est un vert qui ment).

Porteur : `darkaSternguard` << Ramus >>, HERO hors catalogue (`catalog_inject --missing`).
Cibles : `astraBullgryn` et `necroWarden`, placees ADJACENTES.
ASCII only. Probe jumeau : `scripts/python/probe_419r1tr11_combi_melta.py` (montage + mesure).
"""
from __future__ import annotations

import uuid

import pytest

import probe_419r1tr11_combi_melta as P
from engine.entities.effect_type import EffectType


EPS = P.EPS

# Les DEUX effets de la face COMBAT de 1545 (`SpecialIssueCombiMelta_InitAbility$$CreateBehaviour`
# = `AddEffect(0x61b) & AddEffect(0x61c)`). ⚠ Ces ids vivent dans un espace de numerotation
# DIFFERENT de l'ability 1545 : ils sont RE-DERIVES de l'enum du port (mirror 1:1 du natif), jamais
# recopies d'une fiche.
_COMBAT_EFFECTS = (int(EffectType.SpecialIssueCombiMelta_AdditionalHits),      # 1563
                   int(EffectType.SpecialIssueCombiMelta_ExtraDmg))            # 1564

#: Distance a laquelle mord le descripteur 1563 (`DSLFormulas+0x28 = Const(2)`) -- c'est la seule
#: ou le bi-canal ROLL/DISPLAY peut se voir sur ce montage.
_AH_DIST = 2


def _arm(build_runner, live_session, rpc, writer):
    """Monte le bras : seed BC ecrit par `writer`, runner, puis le montage du probe."""
    P.LOGS.mkdir(parents=True, exist_ok=True)
    bc = P.LOGS / ("tr11-seedbc-%s.json" % uuid.uuid4().hex[:8])
    path = writer(bc)
    rid = build_runner(seed=P.SEED, extra=["--seed-bc", str(path), *P.BUILD_ARGS])["rid"]
    try:
        return P.build_case(live_session, rpc, rid)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def raw(build_runner, live_session, rpc):
    """Le SEUL bras : aucun patch de BC, la configuration reelle du jeu."""
    return _arm(build_runner, live_session, rpc, P.write_raw_seed_bc)


@pytest.fixture(scope="module")
def raw_rows(raw, rpc):
    return P.measure(rpc, raw)


def test_combat_face_is_registered():
    """(4) OFFLINE -- la face COMBAT de 1545 EST au registre.

    Pendant EXACT de l'ancien `test_neutered_arm_condition_of_validity`, dans l'autre sens : ce
    fichier ne monte plus qu'un bras PARCE QUE le port modelise 1563/1564. Si une des deux entrees
    disparaissait, les mesures ci-dessous redeviendraient fausses aux distances 1 et 2 (elles y
    divergeaient de 8.35 a 78.01 points) et il faudrait remonter le bras `neutered`.

    Le critere est DERIVE du registre, jamais saisi."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    missing = [EffectType(e).name for e in _COMBAT_EFFECTS
               if EffectType(e).name not in EFFECT_CLASSES]
    assert not missing, (
        "la face COMBAT de SpecialIssueCombiMelta n'est plus au registre `EFFECT_CLASSES` (%s "
        "manquant) : les assertions de ce fichier confrontent un port qui ignore les effets "
        "1563/1564 a un natif qui les applique. A refaire : re-inscrire les deux effets, ou "
        "remonter le bras `neutered` de ce montage (variables de degat de 1545 forcees a 0 dans le "
        "seed BC) AVEC ses trois entrees dans "
        "`probe_366_r1_bcpatch_port_blindspot._EXCEPTIONS`." % ", ".join(missing))


def test_pair_utility_matches_native_on_all_distances(raw_rows):
    """(1) CONFORMITE : port == natif sur chaque (tuile, cible), aux trois distances, SANS PATCH
    et **SANS AUCUNE EXEMPTION** (`#419-r1-tr11-r5` ferme : le bi-canal ROLL/DISPLAY est modelise).

    MESURE au moment de la fermeture (26 lignes) : 22/26 en accord et |ecart| max **0.960412**
    avant, **26/26 et 0.000000** apres."""
    assert raw_rows, "aucune mesure produite -- le montage n'a rien confronte"
    seen = {r["dist"] for r in raw_rows}
    assert {1, 2, 3} <= seen, ("les trois distances ne sont pas mesurees (vues : %s) -- le gate "
                               "`== 3` ne serait pas pris dans les deux sens" % sorted(seen))
    for r in raw_rows:
        assert abs(r["native"] - r["port"]) < EPS, (
            "pairUtility != natif sur %s (d=%d) depuis %s : natif=%r port=%r ecart=%r"
            % (r["target"], r["dist"], r["tile"], r["native"], r["port"],
               r["port"] - r["native"]))


def test_bi_channel_display_is_modelled_and_discriminant():
    """(5) `#419-r1-tr11-r5` FERME -- et ce test EMPECHE le vert de (1) d'etre VIDE.

    Ce qui a ete corrige : le descripteur 1563 ne publiait QUE `min`/`max`, donc la face
    PREDICTION du port lisait `predefined = [min, max]` la ou le natif lit une cellule
    DEGENEREE. Corps LU de `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this,
    isPrediction, 0xc = minDmg, 0xd = maxDmg)` :
        isPrediction == 0 -> `DSLFormulas.RandomAmount(ConfigVar(min), ConfigVar(max))`  # ROLL
        isPrediction != 0 -> `DSLFormulas.Average(ConfigVar(min), ConfigVar(max))`       # DISPLAY
    et `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` pose
    `min = max = <+0x10 = noeud DISPLAY>.Calculate()` quand `useDisplay`, sinon
    `CalculateMin`/`CalculateMax` du noeud ROLL. `DSLFormulas$$Average` =
    `DivideAmount(Sum(a, b), Direct(2))` -> `AAmountFormula$$RoundFix64Result(., 0)` =
    `Fix64.Round` demi-vers-le-PAIR -- un ENTIER, jamais un `.5`.

    ⚠ CE QUE CE MONTAGE NE DISCRIMINE PAS, ET IL FAUT LE DIRE : au niveau servi
    (`ability_level = 50`, `multiplier = 180`) les bornes valent `[3589, 4387]`, de somme PAIRE ->
    `Fix64.Round` et la moyenne exacte `.5` rendent LE MEME entier. La contre-epreuve a ete JOUEE
    (mutant `amount = (min + max) / 2` sans arrondi) : elle rend **26/26 a 0.000000**, comme le
    port non mute. L'arrondi demi-vers-le-PAIR n'est donc etabli QUE par le decompile, et le
    montage ne peut pas le separer -- il faudrait un couple (niveau, multiplicateur) de somme
    IMPAIRE (195 des 450 balayes le sont, ex. `mult = 180, lvl = 21` -> `[360, 441]`).

    Ce qui EST discriminant ici, et que ce test garde : le rapport `max / min`. Les deux modeles
    (`[min, max]` du port et `avg +/- 20 %` du natif) coincident EXACTEMENT ssi `max == 1.5 x min`
    -- c'est pourquoi le bug etait invisible sur `SquigHound` / `CordClaw` (ratio ~1.503). Ici le
    ratio vaut ~1.222, donc le vert de (1) mesure vraiment quelque chose."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.magnitude import ability_var
    from engine.dsl.base import _round_fix64
    from fractions import Fraction

    name = EffectType.SpecialIssueCombiMelta_AdditionalHits.name
    assert name in EFFECT_CLASSES, (
        "%s n'est plus au registre `EFFECT_CLASSES` : le bi-canal ne peut plus etre garde" % name)

    lvl, mult = 50, 180                      # le regime SERVI par `buildNormalizedBC` sur ce montage
    mn = ability_var("SpecialIssueCombiMelta", "minDmg", lvl, multiplier_pct=mult)
    mx = ability_var("SpecialIssueCombiMelta", "maxDmg", lvl, multiplier_pct=mult)
    assert mn and mx, "bornes minDmg/maxDmg introuvables au gameconfig (L%d, mult %d)" % (lvl, mult)
    ratio = float(mx) / float(mn)
    assert abs(ratio - 1.5) > 1e-3, (
        "max / min == %.4f : a ce rapport, `[min, max]` et `avg +/- 20 %%` COINCIDENT -- le vert de "
        "(1) ne separerait plus les deux modeles, et ce montage cesserait de garder le bi-canal. "
        "Choisir un porteur/niveau au rapport different." % ratio)

    eff = EFFECT_CLASSES[name](name=name, level=1, ability_level=lvl,
                               ability_variables_multiplier=mult)
    grp = (eff.additional_hit_groups({"att_pos": (0, 0), "t_pos": (2, 0)}) or [None])[0]
    assert grp, "le descripteur 1563 ne rend rien a d == %d -- le gate IsAtRange a change" % _AH_DIST
    assert grp.get("min") == int(mn) and grp.get("max") == int(mx), (
        "canal COMBAT (noeud ROLL) altere : attendu [%d, %d], lu %r"
        % (int(mn), int(mx), (grp.get("min"), grp.get("max"))))
    expected_avg = _round_fix64(Fraction(int(mn) + int(mx), 2), 0)
    assert grp.get("amount") == expected_avg, (
        "canal PREDICTION (noeud DISPLAY) : attendu `Fix64.Round((%d + %d) / 2)` = %r, lu %r -- "
        "sans lui la prediction du port publie `predefined = [min, max]` et diverge du natif "
        "(mesure a la fermeture : 4 lignes a -0.960412)"
        % (int(mn), int(mx), expected_avg, grp.get("amount")))


def test_term_is_exactly_the_weight_at_range_3(raw, raw_rows):
    """(2) DISCRIMINANCE : playbook 1545 RETIRE -> le port perd EXACTEMENT le poids BC aux tuiles a
    distance 3, et RIEN aux distances 1 et 2. Plus aucune exemption (`#419-r1-tr11-r5` ferme)."""
    weight = raw["weight"]
    assert weight != 0, ("le BC servi porte %s = 0 : le regime ne discrimine rien" % P.WEIGHT_KEY)
    for r in raw_rows:
        expected = weight if r["dist"] == P.RANGE else 0.0
        got = r["native"] - r["port_muted"]
        assert abs(got - expected) < EPS, (
            "sans le playbook %d, l'ecart au natif sur %s (d=%d) depuis %s devrait valoir "
            "exactement %r : natif=%r port_mute=%r ecart=%r"
            % (P.ABILITY, r["target"], r["dist"], r["tile"], expected, r["native"],
               r["port_muted"], got))


def test_target_read_is_the_case_target(raw, raw_rows):
    """(3) La distance est prise sur `case.Target` (`UtilityAttackCase@+0x20`).

    Depuis une MEME tuile, les deux cibles sont a des distances differentes dont l'une vaut 3 :
    une seule des deux lignes porte le poids. Un port qui lirait l'ennemi le plus proche, le
    caster, ou une cible fixe rendrait la meme valeur sur les deux."""
    weight = raw["weight"]
    by_tile: dict = {}
    for r in raw_rows:
        by_tile.setdefault(r["tile"], {})[r["target"]] = r
    split = [(t, m) for t, m in by_tile.items()
             if len(m) == 2 and len({x["dist"] for x in m.values()}) == 2
             and P.RANGE in {x["dist"] for x in m.values()}]
    assert split, ("aucune tuile d'ou les deux cibles soient a des distances DIFFERENTES dont "
                   "l'une vaut 3 -- la lecture de `case.Target` n'est pas exercee")
    for tile, m in split:
        terms = {vis: x["native"] - x["port_muted"] for vis, x in m.items()}
        dists = {vis: x["dist"] for vis, x in m.items()}
        for vis, term in terms.items():
            expected = weight if dists[vis] == P.RANGE else 0.0
            assert abs(term - expected) < EPS, (
                "depuis %s, la cible %s est a distance %d : le terme natif devrait valoir %r, "
                "mesure %r (distances = %r, termes = %r)"
                % (tile, vis, dists[vis], expected, term, dists, terms))


def test_every_reading_has_a_regime_where_its_mutant_bites(raw, rpc):
    """(6) Six contre-epreuves, chacune avec sa RECIPROQUE.

    Le critere est le DEPLACEMENT du port par rapport au NATIF : sur ce bras le port NON MUTE colle
    au natif au bit pres partout hors du regime residuel (tests 1 et 5), donc tout ecart >= 1 point
    EST le mutant. Chaque mutant doit (a) s'ecarter d'au moins 1 point dans au moins une distance et
    (b) rester INERTE sur au moins une ligne -- une contre-epreuve qui mord partout ne discrimine
    rien."""
    for name in sorted(P.MUTANTS):
        rows = P.run_mutant(rpc, raw, name)
        per = P.mutant_bite(rows)
        inert = P.mutant_inert_lines(rows)
        assert per and max(per.values()) >= 1.0, (
            "le mutant %r ne DEPLACE rien (%r) : la lecture qu'il casse n'est exercee par aucun "
            "regime du montage -- la garde ne la protege pas" % (name, per))
        assert inert > 0, (
            "le mutant %r s'ecarte du natif sur TOUTES les lignes : la contre-epreuve ne "
            "discrimine aucun regime" % name)
