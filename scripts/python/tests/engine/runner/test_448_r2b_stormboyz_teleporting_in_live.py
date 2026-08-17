"""GARDE LIVE #448-r2b tranche 2/4 -- `1140 StormboyzStrike_TeleportingIn` confronte au natif.

LES QUATRE CRITERES, en questions binaires :

  1. **Le pas de teleport pose-t-il un marqueur `*_Moving` ?** -- non, et c'est la branche
     `Nothing()` de T4, seule de la famille. Pose au PORT (le pas rejoue OFFLINE, PRNG aligne, les
     deux etats intermediaires captes par instrumentation) et au NATIF (`applyAction move` + scan
     de la CASCADE d'events).
  2. **QUEL ETAGE retire 1140 pendant le pas ?** -- `...StormboyzStrike_MissAbility`, au
     `On(0x1f = PreUnitMove)` : son `RemoveEffect(Caster, 0x474)` est HORS du `If`, donc il tombe
     que le hex ait ete rate ou non. T1 (`On(0x04)`) n'a alors plus rien a retirer. Mesure d'ETAGE
     des deux cotes : etat AVANT/APRES le vecteur `On(0x1f)` cote port, rang du retrait par rapport
     au `ChangePosition` dans la cascade cote natif.
  3. **Le gate `HasTile(Owner)` de T3 tient-il sur son bras FAUX ?** -- 1140 est le SEUL regime du
     build qui l'exerce (1035, 1238 et 1573 laissent leur porteur SUR le plateau). Il n'est plus
     exercable par un GESTE depuis que `...StormboyzStrike_FallbackAbility` est portee (elle repose
     l'unite AVANT que T3 soit evalue) -> le probe l'isole en RETIRANT le Fallback du registre.
  4. **Le finish nominal rejoint-il le natif ?** -- Fallback (repose l'unite) puis T3 (`HasTile`
     devenu VRAI, retire 1140), TERME A TERME, PRNG aligne.

Le montage vit dans `scripts/python/probe_448_r2b_stormboyz_teleporting_in.py` (`run()`) ; ce
fichier n'en est que la PORTE pytest. Porteur reel `orksNpc6Stormboy` = **npc** sans summoner ->
GREFFE du passif sur une unite du pool (`case-92` §5bis), deja outillee et validee par #366-r1.

⚠ CE QUE #448-r3-r1 A CORRIGE ICI. Trois assertions de ce fichier decrivaient le port du
2026-08-01, ou `...StormboyzStrike_MissAbility` et `...StormboyzStrike_FallbackAbility` n'etaient
PAS portees. `9fc0deca` (#448-r1, 2026-08-03) les a portees toutes les deux : le Miss retire 1140
au pre-move, le Fallback repose l'unite au finish. Les assertions exigeaient donc du port qu'il
S'ECARTE du natif -- elles rougissaient a bon droit, en accusant le port.
Et le PROBE, lui, ne mesurait rien EN CLI : sans transport RPC ambiant (`snapshot.bind_live_rpc`,
que `tests/conftest.py::live_session` lie et qu'un lancement direct ne liait pas), la greffe n'est
pas montee cote port et toutes les assertions NEGATIVES passent a vide. D'ou
`test_the_graft_is_actually_mounted_port_side`, qui exige que le registre ait mordu.

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : `run()` leve. Seule
l'indisponibilite du HARNAIS skippe, et c'est `live_session` qui la porte.

RE : `docs/rl/case-448-r2b-stormboyz-teleporting-in.md`, `docs/rl/case-448-r1-stormboyz-fallback-miss.md`
et `docs/rl/case-448-r3-r1-etage-entre-depuis.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import pytest

import probe_448_r2b_stormboyz_teleporting_in as P

TELEPORTING_IN = 1140
MOVING_TYPES = (1036, 1241, 1574)          # les TROIS `*_Moving` du build -- aucun n'est Stormboyz


@pytest.fixture(scope="module")
def stormboyz_teleporting_cases(live_session):
    """Le montage, UNE fois pour tout le fichier : un cas par entree de `P.TEST_PLAN` (base WALK et
    base FLY). `run()` DISPOSE ses runners en sortie -- rien a liberer au teardown."""
    return [P.run(board, seed, graft, foes) for board, seed, graft, foes in P.TEST_PLAN]


def _tag(c):
    return "%s/%s" % (c.get("graft"), c.get("board"))


def test_the_montage_actually_mounted_the_grafted_passive(stormboyz_teleporting_cases):
    """ANTI-TAUTOLOGIE, volet NATIF. Sans ce test, un montage qui n'aurait RIEN greffe laisserait le
    porteur sur le plateau SANS 1140, et les confrontations « rien d'un cote, rien de l'autre »
    seraient toutes vertes. On exige l'etat de depart NATIF : hors plateau, vivant, 1140 a
    `remaining = 2` (`AddEffect(..., turns: Nullable<int>(2))` -- deja en TOURS ;
    `TurnsFromRounds(2)` vaudrait 4)."""
    for c in stormboyz_teleporting_cases:
        assert c["graftReport"]["abilityId"] == 1141, c["graftReport"]
        s = c["start"]
        assert s["pos"] is None and s["feet"] == [], (
            "%s le porteur NATIF garde une position : %r" % (_tag(c), s))
        assert s["alive"] is True
        assert [tuple(r) for r in s["effects"] if r[0] == TELEPORTING_IN] == [(TELEPORTING_IN, 2)], (
            "%s effets de depart = %r" % (_tag(c), s["effects"]))


def test_the_graft_is_actually_mounted_port_side(stormboyz_teleporting_cases):
    """ANTI-TAUTOLOGIE, volet PORT -- et c'est le test que #448-r3-r1 a du AJOUTER.

    Toutes les confrontations de ce fichier sont des NEGATIFS (« 1140 n'est plus la », « aucun
    `*_Moving` ») : un port qui n'aurait monte AUCUNE des trois classes de `StormboyzStrike` les
    rendrait TOUTES vertes. C'est exactement ce qui se produisait quand le probe etait lance hors
    pytest -- `UnitContext.passive_abilities` n'est seede que si le transport RPC ambiant est lie,
    sinon `collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>)`, qui ne porte pas
    l'ability GREFFEE.

    Les TROIS classes doivent etre montees : le builder natif
    `AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_134` construit une
    `List` de trois instances pour le seul `TriggeredAbilityType.StormboyzStrike` (case-448-r1 §1),
    donc greffer le passif les monte toutes."""
    for c in stormboyz_teleporting_cases:
        assert c["ported"] == P.STORMBOYZ_PORTED, (
            "%s le port n'a monte que %r au lieu de %r -- les assertions NEGATIVES de ce fichier "
            "ne mesureraient RIEN" % (_tag(c), c["ported"], P.STORMBOYZ_PORTED))


def test_the_carrier_under_1140_is_untargetable_and_uncastable(stormboyz_teleporting_cases):
    """`IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal` ->
    `UnitFlagsComponent$$Add(0x11)` : le flag vient de la BASE, donc de 1140 aussi. Cote NATIF, le
    corollaire mesurable est que le porteur n'a AUCUNE cible « sans bouger » -- ce qui est aussi la
    raison pour laquelle T2 (`On(0x2a PreUnitAbility)`) n'est PAS exercable par un geste."""
    for c in stormboyz_teleporting_cases:
        assert c["start"]["untargetable"] is True, _tag(c)
        # #433-r3-r2-r1 -- LE CANAL FLAG, ET SA GARDE DE NON-DEGENERESCENCE. `cmp_terms` compare
        # desormais `flagUntargetable` terme a terme entre le port et l'etat RECONSTRUIT du natif
        # (dont le `UnitFlagsComponent` est seede par `combatSnapshot.units[].unitFlags`, donc par
        # le jeu). Un accord sur deux `False` ne prouverait RIEN : cette assertion exige que le
        # canal soit VRAI ici, c'est-a-dire que la comparaison porte sur un temoin non nul.
        assert c["start"]["flagUntargetable"] is True, (
            "%s le canal FLAG du port ne voit pas `UnitFlag.Untargetable` sur un porteur de 1140 "
            "-- `AddEffectOperation._apply_untargetable_flag` ne mord pas en live, et l'accord de "
            "`cmp_terms` sur cette cle serait un accord en regime DEGENERE" % _tag(c))
        assert c["fromHere"] == [], (
            "%s le natif propose des cibles a une unite hors plateau : %r" % (_tag(c),
                                                                             c["fromHere"]))


def test_the_teleport_step_poses_no_moving_marker_at_all(stormboyz_teleporting_cases):
    """LA question binaire #1 -- la branche `Nothing()` de T4, des DEUX cotes.

    Cote PORT : l'etat capte a l'entree du vecteur after-move -- la seule fenetre ou un `*_Moving`
    serait visible, puisque son propre trigger le retire a ce vecteur -- ne doit contenir AUCUN des
    trois `*_Moving` du build.
    Cote NATIF : la cascade d'events du pas ne porte aucun groupe `Effect_Refresh <<*_Moving>>`.
    TEMOIN POSITIF du meme scan : la tranche 1 (#448-r2, `eldarAutarch`) y remonte DEUX
    `<<TeleportStrike_Moving>>` encadrant le `ChangePosition`. Une cascade VIDE ne prouverait
    rien -> on l'exige non vide."""
    for c in stormboyz_teleporting_cases:
        assert not [e for e in c["moveMid"] if e in MOVING_TYPES], (
            "%s le port a pose un `*_Moving` PENDANT le pas : %r" % (_tag(c), c["moveMid"]))
        assert TELEPORTING_IN not in c["moveEnd"], (
            "%s 1140 SURVIT au pas cote port" % _tag(c))
        assert c["cascadeCount"] > 0, (
            "%s cascade NATIVE vide -- le scan `*_Moving` ne mesure RIEN" % _tag(c))
        assert c["movingHits"] == [], (
            "%s la cascade NATIVE porte un `*_Moving` : %r" % (_tag(c), c["movingHits"]))


def test_the_miss_ability_is_what_removes_1140_during_the_step(stormboyz_teleporting_cases):
    """LA question binaire #2 -- QUEL ETAGE retire 1140 pendant le pas. Ce n'est pas T1.

    `...StormboyzStrike_MissAbility$$CreateBehaviour` ecoute `On(0x1f = PreUnitMove)` et son
    `RemoveEffect( Caster@Sel+0x48, Nullable(0x474) )` est **HORS du `If(Maybe(chance))`** : il
    tombe que le hex ait ete rate ou non. T1 (`On(0x04) & OwnerIsActor`) n'a donc plus rien a
    retirer quand le vecteur after-move s'ouvre.

    On l'ATTRIBUE au lieu de le constater, des deux cotes :
      * PORT -- 1140 est LA a l'entree du vecteur `On(0x1f)` et PARTI a sa sortie, et le vecteur a
        RENDU le resultat du Miss (`class: "Miss"`). Un simple « 1140 n'est plus la a la fin »
        passerait aussi sur un port qui ne monte rien ;
      * NATIF -- dans la cascade, le retrait de 1140 precede le `ChangePosition`. Un retrait par T1
        serait APRES : c'est la meme borne que #448-r3 emploie pour montrer que `1036` ENCADRE le
        deplacement."""
    for c in stormboyz_teleporting_cases:
        assert TELEPORTING_IN in c["premoveBefore"], (
            "%s 1140 absent AVANT le vecteur `On(0x1f)` -- rien n'est mesure : %r"
            % (_tag(c), c["premoveBefore"]))
        assert TELEPORTING_IN not in c["premoveAfter"], (
            "%s 1140 SURVIT au vecteur `On(0x1f)` -- le `RemoveEffect(Caster, 0x474)` du "
            "`_MissAbility` n'a pas joue : %r" % (_tag(c), c["premoveAfter"]))
        assert c["missResult"] is not None, (
            "%s `...StormboyzStrike_MissAbility` n'a rien RENDU sur `On(0x1f)` -- le retrait de "
            "1140 n'est attribuable a aucun etage" % _tag(c))
        assert TELEPORTING_IN not in c["moveMid"], (
            "%s 1140 encore la a l'entree du vecteur after-move : %r" % (_tag(c), c["moveMid"]))
        assert c["nativeRemoveIdx"] is not None, (
            "%s la cascade NATIVE ne porte AUCUN retrait de 1140" % _tag(c))
        assert c["nativeChangePosIdx"] is not None, (
            "%s aucun `ChangePosition` dans la cascade NATIVE -- la borne d'etage n'existe pas"
            % _tag(c))
        assert c["nativeRemoveIdx"] < c["nativeChangePosIdx"], (
            "%s le natif retire 1140 APRES le ChangePosition (rem=%r, cp=%r) -- ce serait T1 "
            "(`On(0x04)`) et non le `_MissAbility` (`On(0x1f)`)"
            % (_tag(c), c["nativeRemoveIdx"], c["nativeChangePosIdx"]))


def test_port_and_native_agree_after_the_teleport_step(stormboyz_teleporting_cases):
    """La confrontation du pas, TERME A TERME (position, empreinte, vie, LISTE ENTIERE des effets,
    non-ciblabilite).

    Le terme POSITION est compare A L'IDENTIQUE, et c'est l'ALIGNEMENT PRNG qui le permet : le
    `_MissAbility` tire `Maybe(chance = 20)` puis, si le hex est rate,
    `PickRandomly(CanAddUnit(AdjacentTiles(<dest>)), 1)` -- les deux cotes partant du meme etat MT
    (`dumpRng`), la deviation tombe des DEUX cotes ou d'AUCUN. Le seuil mou « distance 0 ou 1 »
    d'avant #448-r3-r1 acceptait, lui, un vrai desaccord de port du moment qu'il restait adjacent."""
    for c in stormboyz_teleporting_cases:
        assert c["moveMutated"] is True, (
            "%s le move live n'a RIEN mute (H55, no-op silencieux) -- montage" % _tag(c))
        p, n = c["portMove"], c["nativeMove"]
        assert not [r for r in n["effects"] if r[0] == TELEPORTING_IN], (
            "%s le NATIF garde 1140 apres le pas -- la mesure ne discrimine rien" % _tag(c))
        assert p["effects"] == n["effects"], "%s port=%r natif=%r" % (_tag(c), p["effects"],
                                                                      n["effects"])
        assert p["alive"] == n["alive"] and p["untargetable"] == n["untargetable"], \
            "%s port=%r natif=%r" % (_tag(c), p, n)
        assert p["pos"] == n["pos"] and p["feet"] == n["feet"], (
            "%s atterrissage port=%r natif=%r (deviation du `_MissAbility` mesuree a %r hex ; "
            "PRNG aligne, donc un ecart EST un desaccord de port)"
            % (_tag(c), p["pos"], n["pos"], c["missDistance"]))


def test_the_hastile_gate_of_T3_still_holds_on_its_false_arm(stormboyz_teleporting_cases):
    """LA question binaire #3 -- le gate `HasTile(Owner)` de T3, sur son bras FAUX.

    C'est le contre-bras qu'aucune autre tranche de la famille ne peut exercer : 1035, 1238 et 1573
    laissent leur porteur SUR le plateau. Un port qui perdrait le gate retirerait l'effet des le
    `On(0x28)` -- l'unite redeviendrait ciblable et sortirait du pathfinder de teleport en pleine
    descente (degradation PERMISSIVE et silencieuse).

    ⚠ CE BRAS N'EST PLUS ATTEIGNABLE PAR UN GESTE, et c'est un fait du NATIF, pas une limite du
    banc : `...StormboyzStrike_FallbackAbility` ecoute le MEME `On(0x28)`, c'est une ABILITY (donc
    evaluee AVANT les effets, cf. `dispatch/core.py::evaluate_trigger_operation`), et son
    `MoveUnitBehaviour` repose l'unite -- si bien que T3 voit toujours `HasTile` VRAI. Le probe
    l'isole en RETIRANT le Fallback du registre, en DEUX lectures : `matches()` de T3 sur l'etat
    hors plateau (l'etage seul), puis le vecteur `On(0x28)` prive de Fallback (l'etage dans son
    vecteur). Volet PORT-SEUL assume : le natif ne peut pas produire ce regime."""
    for c in stormboyz_teleporting_cases:
        assert c["t3MatchesOffBoard"] is False, (
            "%s `matches()` de T3 rend VRAI sur une unite HORS PLATEAU -- le gate `HasTile(Owner)` "
            "est perdu" % _tag(c))
        g = c["finishNoFallback"]
        assert [r for r in g["effects"] if r[0] == TELEPORTING_IN], (
            "%s sans le Fallback, le port RETIRE quand meme 1140 sur une unite HORS PLATEAU -- "
            "gate `HasTile` perdu : %r" % (_tag(c), g))
        assert g["pos"] is None and g["feet"] == [], (
            "%s sans le Fallback, l'unite a ete REPOSEE -- un autre etage lui rend une tuile et la "
            "lecture du gate ne tient plus : %r" % (_tag(c), g))


def test_T3_still_removes_1140_when_it_is_the_only_stage_that_can(stormboyz_teleporting_cases):
    """Le bras VRAI du gate -- et le SEUL regime ou T3 decide encore SEUL.

    ⚠ MESURE #448-r3-r1, et c'est la raison d'etre de ce test : sur le geste NOMINAL, les quatre
    `Triggered()` propres de 1140 sont devenus OBSERVATIONNELLEMENT INERTES, masques par le kit qui
    les entoure -- T1 parce que le Miss a deja retire l'effet au `On(0x1f)` ; T2 parce qu'aucun cast
    n'est legal hors plateau ; T3 parce que le `MoveUnitBehaviour` du Fallback re-emet `On(0x1f)`,
    donc le Miss retire la AUSSI ; T4 parce que sa branche est `Nothing()`. Vider
    `EFFECT_TRIGGERS[1140]` laissait alors le probe ENTIEREMENT VERT : une contre-epreuve PERIMEE
    PAR UN CANAL REDONDANT, exactement le vice que ce fichier vient de corriger ailleurs.

    Le regime qui rend la main a T3 : l'unite POSEE (`HasTile` vrai) et AUCUN mouvement dans le
    vecteur, donc pas de `On(0x1f)` et pas de Miss. La tuile est celle que le NATIF a choisie -- la
    sortie OBSERVEE du Fallback, pas une position inventee."""
    for c in stormboyz_teleporting_cases:
        p = c.get("finishT3Positive")
        assert p is not None, (
            "%s le bras T3-POSITIF n'a pas ete joue -- le natif n'a pas repose l'unite, donc il n'y "
            "avait pas de tuile OBSERVEE ou la poser" % _tag(c))
        assert not [r for r in p["effects"] if r[0] == TELEPORTING_IN], (
            "%s l'unite est POSEE et aucun mouvement n'a eu lieu, mais 1140 SURVIT -- T3 n'a pas "
            "retire : %r" % (_tag(c), p))


def test_the_native_lands_the_carrier_through_the_fallback(stormboyz_teleporting_cases):
    """Le volet NATIF de la question #4. Sur le `finish`, le natif repose l'unite ET retire 1140 :
    c'est `...StormboyzStrike_FallbackAbility` (`On(0x28) & HasEffect(Owner, 0x474)` ->
    `MoveUnitBehaviour(...)`) qui rend `HasTile` vrai -- puis T3 qui retire. Les deux lectures se
    recoupent, et c'est ce que `case-448-r1` §5 mesure independamment."""
    for c in stormboyz_teleporting_cases:
        n = c["finishNative"]
        assert n["pos"] is not None, (
            "%s le natif a laisse l'unite hors plateau -- le Fallback n'a pas fire" % _tag(c))
        assert not [r for r in n["effects"] if r[0] == TELEPORTING_IN], (
            "%s le natif GARDE 1140 apres le finish -- la lecture de T3 tombe" % _tag(c))
        assert n["untargetable"] is False


def test_the_port_rejoins_the_native_on_the_nominal_finish(stormboyz_teleporting_cases):
    """LA question binaire #4, cote PORT : le MEME `On(0x28)` joue NOMINALEMENT (Fallback puis T3)
    doit rendre l'etat du natif, TERME A TERME -- position, empreinte, vie, liste ENTIERE des
    effets, non-ciblabilite.

    Le pas fait travailler tout le kit d'un coup : `On(0x28)` -> Fallback -> `MoveUnit` ->
    `On(0x1f)` -> Miss (`Maybe(20)`, deviation, `RemoveEffect(1140)`, `TriggerAbility(FullThrottle)`)
    -> `AddEffect(1179)` sur le noeud re-evalue -> puis T3, `HasTile` devenu vrai. Le PRNG etant
    aligne sur le natif, la tuile d'atterrissage est DETERMINISTE des deux cotes.

    ⚠ Ce test REMPLACE l'ancien `test_injecting_the_missing_stage_...`, qui posait l'unite la ou le
    natif l'avait posee avant de re-emettre l'evenement : depuis que le Fallback est porte, cette
    injection ne mesurait plus qu'elle-meme."""
    for c in stormboyz_teleporting_cases:
        a, n = c["finishPortA"], c["finishNative"]
        assert not [r for r in a["effects"] if r[0] == TELEPORTING_IN], (
            "%s le port GARDE 1140 apres le finish -- Fallback ou T3 n'a pas joue : %r"
            % (_tag(c), a))
        assert a["pos"] is not None, (
            "%s le port a LAISSE l'unite hors plateau -- le `MoveUnitBehaviour` du Fallback n'a pas "
            "joue : %r" % (_tag(c), a))
        assert a == n, "%s port=%r natif=%r" % (_tag(c), a, n)


def test_the_carrier_already_carries_its_owner_effects_under_1140(stormboyz_teleporting_cases):
    """POURQUOI 1140 NE PORTE PAS `_TeleportStrikeLandingMixin`. Le regime << passives DEFEREES >>
    de 1035 tient a ce que l'effet est la AVANT que les abilities du porteur soient initialisees.
    Pour 1140 c'est l'INVERSE : `...StormboyzStrike_TeleportAbility$$CreateTrigger` est
    `On(0x21 = AbilityInit)`, donc l'effet arrive PENDANT l'initialisation et les owner-effects du
    porteur sont deja poses. Mesure : au moins un montage montre le porteur sous 1140 portant DEJA
    d'autres effets, et ceux-la ne peuvent venir que de la CAPTURE NATIVE (`snapshot.load_state` ne
    seede que les owner-effects d'ABILITY, et `_seed_trait_owner_effects` n'est appele que par
    `initialize_deferred_actor_abilities`, que cette tranche n'accroche pas)."""
    seen = [c for c in stormboyz_teleporting_cases if c.get("startOthers")]
    assert seen, (
        "aucun montage ne montre d'owner-effect deja pose sous 1140 -- la lecture << pas de "
        "passives deferrees >> n'est pas mesuree ; choisir un greffon qui en porte")
    for c in seen:
        assert all(r[0] != TELEPORTING_IN for r in c["startOthers"]), c["startOthers"]


def test_the_probe_reports_no_disagreement_at_all(stormboyz_teleporting_cases):
    """Filet : tout desaccord que le probe a releve et qu'aucun test ci-dessus n'aurait couvert."""
    for c in stormboyz_teleporting_cases:
        assert c["fails"] == [], "%s : %r" % (_tag(c), c["fails"])
