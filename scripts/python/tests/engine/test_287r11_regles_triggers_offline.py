"""#287-r11 -- GARDE des trois regles dynamiques de ciblage portees (1200, 1168, 1179).

Le probe LIVE (`probe_287r11_regles_triggers_live.py`) prouve que les trois regles repondent COMME
LE NATIF sur un plateau reel ; ce fichier-ci garde ce que le live ne peut pas atteindre : les bras
qu'aucun montage n'a produits, et surtout les TROIS lectures non triviales de la RE, chacune sous un
MUTANT qui doit faire rougir.

  1. RECENSEMENT      -- les trois ids sont evaluables par le canal `surcharge`, et le bit est pose.
  2. BASCULE 1200     -- les QUATRE bras du couple de seuils, dont « 0 allie adjacent », qu'aucun
                         montage live n'a pu produire (le board n'offrait que trois cibles).
  3. SEUILS 1200      -- le piege central : le CIBLAGE lit `nrOfUnits`/`nrOfUnits_2` (0x78/0x79),
                         le SUMMON lit `nrOfUnits_3`/`nrOfUnits_4` (0x81/0x82). Un substrat SEPARE
                         les deux ; reutiliser les seuils du summon fabriquerait un SUR-refus.
  4. INITIAL 1168     -- `FixedArmorComponent+0x48` est `StatPart.Initial`, PAS la valeur courante.
                         Le substrat porte une armure de base > 0 REDUITE A ZERO : le natif accepte,
                         une lecture `CURRENT` refuserait.
  5. BASCULE 1179     -- caster libre / encercle / encercle AVEC decoy vivant, plus le fait que la
                         regle NE LIT PAS la cible (l'appel a `GetSurroundingEnemies` est mort).
  6. MUTANTS en DELTA -- desarmee, chaque bascule doit S'EFFONDRER. Sans cet etage, les precedents
                         seraient verts sur un port qui ne consulte plus rien.

ASCII only (cp1252). Aucun runner : tout est offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import hexgeo                                                              # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.stats import StatComponent, StatType, UnitStats       # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,   # noqa: E402
                                      StatsComponent, UnitComponent)

SQUIG = int(ActiveAbilityType.SquigLaunchas)          # 1200
ENTROPY = int(ActiveAbilityType.EntropyCannons)       # 1168
DEMAGOGUE = int(ActiveAbilityType.CultDemagogue)      # 1179
IDS = (SQUIG, ENTROPY, DEMAGOGUE)

REFUS = int(TR.TargetMatchesDynamicRule)              # 2


# ================================================================================================
# substrat -- ids d'UNITE derives du board, donc DISJOINTS de ceux des tuiles (#287-r8 §5)
# ================================================================================================

def _ids_hors_board(n: int = 8):
    base = max(P._board().by_id) + 1000
    return [base + i for i in range(n)]


IDS_U = _ids_hors_board()
CASTER = IDS_U[0]
CIBLE = IDS_U[1]


def _regle(aid: int, st, caster_id=CASTER, target_id=CIBLE) -> int:
    return int(P._porteur(int(aid)).get_dynamic_invalid_target_reason(
        st, caster_id, target_id) or 0)


def _voisins_libres(centre, n: int) -> list:
    """`n` voisins hex de `centre` DANS le board du substrat. Un substrat pose sur une case
    inexistante serait vert par vacuite : les deux bras y rendraient le meme verdict."""
    b = P._board()
    v = [c for c in hexgeo.neighbors(centre[0], centre[1]) if b.id_at(c[0], c[1]) is not None]
    assert len(v) >= n, "board du substrat trop petit : %d voisins pour %d demandes" % (len(v), n)
    return v[:n]


# ================================================================================================
# 1. RECENSEMENT
# ================================================================================================

def test_les_trois_ids_sont_evaluables_par_surcharge():
    for aid in IDS:
        assert P.evaluabilite(aid) == "surcharge", (
            "%d n'est plus evaluable par surcharge (%s)" % (aid, P.evaluabilite(aid)))


def test_les_trois_ids_posent_le_bit_au_masque():
    for aid in IDS:
        opts = getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None)
        assert opts is not None and opts.has(TR.TargetMatchesDynamicRule), (
            "%d ne pose plus TargetMatchesDynamicRule : la regle ne serait jamais consultee" % aid)


# ================================================================================================
# 2. BASCULE 1200 -- les QUATRE bras
# ================================================================================================
#
# `SquigLaunchasAbility$$GetDynamicInvalidTargetReason` :
#     (HasMinimumAdjacentOrks(nrOfUnits) || HasMinimumAdjacentFriendlyUnits(nrOfUnits_2)) ? 0 : 2
# `UnitsFromFaction(..., 5 = Orks)` compare le NOM de faction au `FactionId` gameconfig -> les
# visualId doivent etre de VRAIES unites (`orksNob` est Orks, `ultraTitus` ne l'est pas).

CENTRE = (2, 2)


def _substrat_1200(nb_orks: int, nb_amis: int):
    """Caster team1 (loin), cible team2 en `CENTRE`, `nb_orks` Orks + `nb_amis` non-Orks ALLIES DU
    CASTER adjacents a la cible."""
    v = _voisins_libres(CENTRE, nb_orks + nb_amis) if (nb_orks + nb_amis) else []
    unites = [(CASTER, "orksWarboss", 1, 0, 0, []),
              (CIBLE, "necroWarden", 2, CENTRE[0], CENTRE[1], [])]
    for i in range(nb_orks):
        unites.append((IDS_U[2 + i], "orksNob", 1, v[i][0], v[i][1], []))
    for j in range(nb_amis):
        c = v[nb_orks + j]
        unites.append((IDS_U[2 + nb_orks + j], "ultraTitus", 1, c[0], c[1], []))
    return P.substrat(unites)


def test_1200_les_quatre_bras():
    """Seuils gameconfig : `nrOfUnits` = 1 Ork, `nrOfUnits_2` = 2 amis."""
    cas = [((1, 0), 0, "1 Ork adjacent -> bras nrOfUnits"),
           ((0, 2), 0, "2 amis non-Orks -> bras nrOfUnits_2"),
           ((0, 1), REFUS, "1 seul ami non-Ork : 1 < 2"),
           ((0, 0), REFUS, "aucun allie adjacent")]
    for (o, a), attendu, libelle in cas:
        got = _regle(SQUIG, _substrat_1200(o, a))
        assert got == attendu, "1200 %s : attendu %s, obtenu %s" % (libelle, hex(attendu), hex(got))


# ================================================================================================
# 3. SEUILS 1200 -- CIBLAGE (0x78/0x79) et non SUMMON (0x81/0x82)
# ================================================================================================

def test_1200_lit_les_seuils_du_CIBLAGE_pas_ceux_du_SUMMON():
    """LE PIEGE CENTRAL DE CET ID. Les deux predicats sont PARTAGES avec `FulfillsSummonCriteria`
    (dans l'`ExecuteBehaviour`), mais sur d'AUTRES constantes : ciblage `nrOfUnits`=1 /
    `nrOfUnits_2`=2 (`GetNumberConstant` 0x78/0x79), summon `nrOfUnits_3`=2 / `nrOfUnits_4`=4
    (0x81/0x82). Reutiliser `squig_launchas_fulfills_summon_criteria` au site de ciblage
    fabriquerait un SUR-refus -- l'inverse exact de la degradation que la tranche corrige.

    ⚠ CE TEST NE ROUGIT PAS SUR L'ARBRE TEMOIN, ET C'EST STRUCTUREL : la faute qu'il garde est un
    SUR-refus, or le temoin est PERMISSIF (il rend 0 partout) -- aucun substrat ne peut distinguer
    « accepte parce qu'il lit le bon seuil » de « accepte parce qu'il ne lit rien ». Il garde donc
    une LECTURE, pas un delta, et il le fait sur les deux canaux qui peuvent glisser
    independamment : l'ORDINAL ecrit au site, et la SEPARATION effective des deux jeux de seuils
    sur un substrat."""
    import gameconfig as GC
    from engine.runner.abilities.orks import (CONST_SL_FRIENDS_TARGET, CONST_SL_ORKS_TARGET,
                                              squig_launchas_fulfills_summon_criteria)
    from engine.runner.abilities.behaviours.context import entities_from_state
    # (a) l'ORDINAL ecrit au site -- fige, pas re-derive du mirror (un renumerotage rendrait
    #     `probe_313` vert alors que la valeur lue aurait change).
    assert (int(CONST_SL_ORKS_TARGET), CONST_SL_ORKS_TARGET.name) == (0x78, "nrOfUnits")
    assert (int(CONST_SL_FRIENDS_TARGET), CONST_SL_FRIENDS_TARGET.name) == (0x79, "nrOfUnits_2")
    # (b) la SEPARATION : sur un substrat a UN SEUL Ork adjacent, le ciblage accepte et le summon
    #     refuse. Si les deux couples coincidaient au gameconfig, le test le DIT au lieu de passer.
    c = (GC.ability("SquigLaunchas") or {}).get("constants") or {}
    ciblage = (int(c["nrOfUnits"]), int(c["nrOfUnits_2"]))
    summon = (int(c["nrOfUnits_3"]), int(c["nrOfUnits_4"]))
    assert ciblage != summon, ("les deux couples de seuils COINCIDENT au gameconfig (%s) : ce test "
                               "ne separe plus rien, le substrat doit etre revu" % (ciblage,))
    st = _substrat_1200(1, 0)                     # UN Ork adjacent
    ents = entities_from_state(st, CASTER, CIBLE)
    assert not squig_launchas_fulfills_summon_criteria(*summon).should_trigger(ents), (
        "le critere de SUMMON doit REFUSER a 1 Ork (seuil nrOfUnits_3 = 2) -- s'il accepte, le "
        "substrat ne separe plus les deux jeux de seuils")
    assert squig_launchas_fulfills_summon_criteria(*ciblage).should_trigger(ents), (
        "le couple de CIBLAGE doit accepter a 1 Ork")
    assert _regle(SQUIG, st) == 0, "le CIBLAGE doit accepter a 1 Ork (seuil nrOfUnits = 1)"


# ================================================================================================
# 4. 1168 -- `FixedArmorComponent+0x48` est `StatPart.Initial`, PAS la valeur courante
# ================================================================================================

def _substrat_1168(initial: int, modification: int):
    """Cible team2 avec un `StatComponent(FIXED_ARMOR)` d'`initial` donne et une modification
    per-source de `modification` (negative = armure REDUITE)."""
    st = P.substrat([(CASTER, "deathCrawler", 1, 0, 0, []),
                     (CIBLE, "ultraTitus", 2, 2, 2, [])])
    e = st.get_entity(CIBLE)
    comp = StatComponent(initial=int(initial))
    if modification:
        comp.modify("src-test", int(modification))
    sc = e.get_component(StatsComponent)
    stats = getattr(sc.ctx, "stats", None) if sc is not None else None
    if stats is None:
        stats = UnitStats()
        sc.ctx.stats = stats
    stats.components[int(StatType.FIXED_ARMOR)] = comp
    return st, comp


def test_1168_lit_INITIAL_et_non_la_valeur_courante():
    """L'armure de BASE vaut 10 et une modification de -10 la ramene a 0. Le natif lit `+0x48` =
    `Initial` (10 > 0) et ACCEPTE ; une lecture `CurrentValue` (`+0x48 + +0x10` = 0) refuserait --
    un SUR-refus exactement dans le regime que l'ability vise (une cible dont on a casse l'armure).

    LE MUTANT EST EXPLICITE, et c'est ce qui rend ce test discriminant : sur un port PERMISSIF (le
    defaut herite), « doit accepter » passerait aussi. On construit donc le MEME arbre avec
    `StatPart.CURRENT` et l'on exige que les deux verdicts DIVERGENT sur ce substrat. Le jour ou le
    port lirait `CURRENT`, la production coinciderait avec le mutant et cette assertion rougirait."""
    from engine.entities.effect_type import EffectType
    from engine.entities.formulas import StatAmount
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.stats import StatPart
    from engine.entities.triggers import (AmountIsGreaterThanZero, HasNegativeModifier,
                                          IsInTeamAura, TriggerAnd, TriggerOr)
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.deathguard import entropy_cannons_is_valid_target_trigger
    st, comp = _substrat_1168(initial=10, modification=-10)
    assert comp.get_current_value() == 0, "le substrat ne met pas la valeur COURANTE a zero"
    assert comp.get_stat_part(int(StatPart.INITIAL)) == 10, "le substrat ne met pas l'INITIAL a 10"
    ents = entities_from_state(st, CASTER, CIBLE)
    mutant = TriggerOr(
        IsInTeamAura(Target(), int(EffectType.ContagionsOfNurgle_ArmorReduction1), Caster()),
        TriggerAnd(HasNegativeModifier(Target(), (int(StatType.FIXED_ARMOR),)),
                   AmountIsGreaterThanZero(StatAmount(Target(), int(StatType.FIXED_ARMOR),
                                                      int(StatPart.CURRENT)))))
    assert entropy_cannons_is_valid_target_trigger().should_trigger(ents) is True, (
        "1168 doit ACCEPTER une armure de BASE > 0 negativement modifiee (lecture StatPart.Initial)")
    assert mutant.should_trigger(ents) is False, (
        "le substrat ne SEPARE plus Initial de Current -- le mutant doit refuser")
    assert _regle(ENTROPY, st) == 0, "le chainon complet doit accepter ce substrat"


def test_1168_refuse_sans_modification_negative_ni_aura():
    st, _c = _substrat_1168(initial=10, modification=0)
    assert _regle(ENTROPY, st) == REFUS, (
        "1168 doit REFUSER une cible sans aura ET sans modification negative de FixedArmor")


def test_1168_refuse_une_armure_de_base_NULLE_meme_negativement_modifiee():
    """L'autre bras du ET : `comp.<+0x48> > 0`. Une cible sans armure de base ne passe pas, meme si
    elle porte une modification negative."""
    st, _c = _substrat_1168(initial=0, modification=-3)
    assert _regle(ENTROPY, st) == REFUS, (
        "1168 doit REFUSER une armure de BASE nulle -- le terme `> 0` du natif serait inerte")


# ================================================================================================
# 5. BASCULE 1179 -- et le fait que la regle NE LIT PAS la cible
# ================================================================================================

COIN = (0, 0)


def _substrat_1179(encercle: bool, avec_decoy: bool):
    """Caster `genesPrimus` dans le COIN. `encercle` : tous ses voisins portent un ENNEMI (le BFS
    ne sort pas et aucune tuile occupee n'entre dans le stop_set). `avec_decoy` : un
    `genesSmnDecoy` VIVANT du meme camp, pose au loin."""
    v = [c for c in hexgeo.neighbors(COIN[0], COIN[1])
         if P._board().id_at(c[0], c[1]) is not None]
    assert len(v) >= 2, "le coin du board du substrat a moins de deux voisins"
    unites = [(CASTER, "genesPrimus", 1, COIN[0], COIN[1], [])]
    if encercle:
        # La CIBLE est le 1er voisin, les autres voisins portent les ennemis qui ferment le BFS.
        unites.append((CIBLE, "necroWarden", 2, v[0][0], v[0][1], []))
        for i, c in enumerate(v[1:]):
            unites.append((IDS_U[2 + i], "necroWarden", 2, c[0], c[1], []))
    else:
        unites.append((CIBLE, "necroWarden", 2, 3, 3, []))
    if avec_decoy:
        unites.append((IDS_U[7], "genesSmnDecoy", 1, 5, 5, []))
    return P.substrat(unites)


def test_1179_bascule_libre_encercle_decoy():
    from engine.runner.abilities.genestealer import (cult_demagogue_free_spawn_tiles,
                                                     cult_demagogue_has_living_decoy)
    libre = _substrat_1179(encercle=False, avec_decoy=False)
    assert cult_demagogue_free_spawn_tiles(libre, CASTER), (
        "le substrat LIBRE ne produit aucune tuile de pose : la bascule serait vraie par vacuite")
    assert _regle(DEMAGOGUE, libre) == 0, "1179 doit ACCEPTER quand une tuile de pose existe"

    encercle = _substrat_1179(encercle=True, avec_decoy=False)
    assert not cult_demagogue_free_spawn_tiles(encercle, CASTER), (
        "le substrat ENCERCLE laisse une tuile de pose : le 1er terme n'est pas neutralise")
    assert not cult_demagogue_has_living_decoy(encercle, CASTER)
    assert _regle(DEMAGOGUE, encercle) == REFUS, (
        "1179 doit REFUSER sans tuile de pose ET sans decoy vivant")

    avec = _substrat_1179(encercle=True, avec_decoy=True)
    assert cult_demagogue_has_living_decoy(avec, CASTER), (
        "le `genesSmnDecoy` du substrat n'est pas vu : le 2e terme ne bascule pas")
    assert _regle(DEMAGOGUE, avec) == 0, (
        "1179 doit ACCEPTER des qu'un decoy est en jeu, meme sans tuile de pose")


def test_1179_ne_lit_PAS_la_cible():
    """L'appel a `GetSurroundingEnemies(target, allAlive, range, 0)` est MORT (son retour est
    ecrase sans etre sauve, lu dans l'assembleur) : les deux termes evalues ne dependent que du
    CASTER. Le verdict doit donc etre IDENTIQUE pour toutes les cibles d'un meme etat -- et c'est
    ce qui rend la bascule inter-montages du probe live necessaire."""
    st = _substrat_1179(encercle=True, avec_decoy=False)
    cibles = [uid for uid, e in st.entities.items()
              if uid != CASTER and e.get_component(PositionComponent) is not None]
    assert len(cibles) >= 2, "substrat a moins de deux cibles : le test ne discrimine rien"
    verdicts = {_regle(DEMAGOGUE, st, target_id=t) for t in cibles}
    assert verdicts == {REFUS}, (
        "1179 rend des verdicts DIFFERENTS selon la cible (%s) : un terme lit la cible, ce que le "
        "decompile ne fait pas" % (verdicts,))


# ================================================================================================
# 6. MUTANTS en DELTA -- desarmee, chaque bascule s'effondre
# ================================================================================================

def test_mutants_en_delta():
    """Chaque cas ci-dessous rend un REFUS avec la regle armee. Desarmee, la classe retrouve le
    defaut herite d'`ActiveAbility` (`return 0`) : le refus doit DISPARAITRE. Sans cet etage, les
    etages 2 a 5 resteraient verts sur un port qui ne consulte plus rien."""
    cas = [(SQUIG, _substrat_1200(0, 0)),
           (ENTROPY, _substrat_1168(initial=10, modification=0)[0]),
           (DEMAGOGUE, _substrat_1179(encercle=True, avec_decoy=False))]
    for aid, st in cas:
        arme = _regle(aid, st)
        assert arme == REFUS, "%d : le substrat n'exerce pas le refus (%s)" % (aid, hex(arme))
        with P.desarme(aid):
            desarme = _regle(aid, st)
        assert desarme == 0, ("%d : le desarmement ne change rien (%s) -- la mesure ne passe pas "
                              "par la regle" % (aid, hex(desarme)))
