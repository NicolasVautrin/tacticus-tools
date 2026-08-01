"""#306 -- sur les vecteurs d'EFFET, la POSE ecrit les DEUX canaux, le RETRAIT n'en ecrit qu'UN.

    `CurrentAbility`    `AbilityEntities+0x60`  ->  `ev.triggering_ability` / `state.triggering_ability`
    `TriggeringAbility` `AbilityEntities+0x98`  ->  `ev.triggering_effect`  / `state.trigger_ability_type`

`IdunBattle.Operations.AddEffectOperation$$Execute` memset son `AbilityEntities` (0x128 octets) puis
appelle le ctor NOMME `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` en lui passant DEUX
`Nullable<AbilityOrEffect>` batis sur le MEME `effectType` -- `currentAbilityOrEffect` (`+0x60`) et
`triggerAbilityOrEffect` (`+0x98`) -- `parentAbilityOrEffect` (`+0x7c`) restant vide.
`IdunBattle.Operations.RemoveEffectOperation$$Execute`, lui, n'appelle AUCUN ctor : apres son memset
il n'ecrit que `+0x10`/`+0x18` (le porteur) et `+0x60..+0x7c` (l'effet retire). Controle NEGATIF fait
a l'assembleur : `+0x98` n'est jamais touche.

Consequence, et c'est ce que ces gardes verrouillent :
  * sur `On(61 = PreEffectAdded)` / `On(62 = EffectAdded)` / `On(70 = UnitBecameUntargetable)`, `CurrentAbilityIs(effet)` ET `TriggeringEffectIs(effet)` sont
    VRAIS -- meme valeur, indiscernables ;
  * sur `On(63 = PreEffectRemoved)` / `On(64 = EffectRemoved)` / `On(59 = UnitBecameTargetable)`, `TriggeringEffectIs` et `TriggeringAbilityIs` sont TOUJOURS
    FAUX, `TriggeringAbilityIsNone` est VRAI, et c'est **`CurrentAbilityIs` qui porte l'effet
    retire** ;
  * le memset ECRASE l'ambiant : une pose faite DANS le behaviour d'une triggered-ability ne laisse
    PAS l'id de cette triggered visible en `+0x60` -- c'est l'EFFET qui l'occupe.

Le port ne posait que `+0x98` a la pose, ne touchait pas l'ambiant, et n'emettait AUCUN vecteur de
retrait. Degradation PERMISSIVE donc muette : aucun test ne rougissait. Ces gardes sont ce qui la
rend detectable. ROUGE mesure sur `origin/master` avant le fix (mode `add_only`) :
`A.matches` y voyait `(ev+0x60, ev+0x98, st+0x60, st+0x98) = (None, 1065, 6161, 6262)`.

TOUT EST OFFLINE et deterministe (zero RNG, zero runner) : la question posee est « quel canal porte
quoi », et elle se tranche sur un `State` nu. La non-regression du COMPORTEMENT observable est
portee par `test_lot_pose_live.py` (le seul consommateur porte de `On(61 = PreEffectAdded)`) et par les tests
d'effets qui traversent la feuille `RemoveEffect`.
"""
from __future__ import annotations

import pytest

import probe_306_effect_trigger_channels as EFC


def test_the_two_channels_are_distinct_slots_on_the_event():
    """Garde de structure : `TriggerEvent` porte DEUX slots distincts. Si quelqu'un refond les deux
    canaux en un seul champ, ce fix redevient un no-op silencieux -- et ce test rougit avant."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.base import TriggerEvent
    assert "triggering_ability" in TriggerEvent.__slots__
    assert "triggering_effect" in TriggerEvent.__slots__
    # Meme vecteur que le reste du fichier, resolu par MEMBRE : l'enum est l'un des QUATRE que la
    # MAJ `gqfc5mff6c` -> `rnca9r7q6c` a renumerotes (#252/#283).
    add = int(EventTriggerType.PreEffectAdded)
    ev = TriggerEvent(add, 1, 2, ranged=False, profile=None, triggering_ability=7)
    assert ev.triggering_effect is None, "ecrire +0x60 a touche +0x98 : les canaux sont aliases"
    ev2 = TriggerEvent(add, 1, 2, ranged=False, profile=None, triggering_effect=8)
    assert ev2.triggering_ability is None, "ecrire +0x98 a touche +0x60 : les canaux sont aliases"


def test_add_writes_both_channels(effect_trigger_channel_case):
    """LE PREMIER FAIT : la POSE remplit `+0x60` ET `+0x98` avec le MEME `AbilityOrEffect`.

    C'est le ctor nomme qui l'etablit sans deduction : `currentAbilityOrEffect` et
    `triggerAbilityOrEffect` recoivent deux `Nullable` construits sur le meme parametre
    `effectType` (l'asm charge `edi` une fois et fait `mov edx, edi` avant chacun des deux
    `AbilityOrEffect$$op_Implicit`)."""
    r = effect_trigger_channel_case()
    for site in EFC.SITES_ADD:
        ev60, ev98, _, _ = EFC.site(r, site)
        assert (ev60, ev98) == (EFC.EFFECT_TYPE, EFC.EFFECT_TYPE), (
            f"'{site}' voit (+0x60, +0x98) = ({ev60}, {ev98}) ; "
            f"AddEffectOperation ecrit les DEUX avec AbilityOrEffect({EFC.EFFECT_TYPE})")


def test_remove_leaves_the_0x98_channel_empty(effect_trigger_channel_case):
    """LE FAIT PRINCIPAL, et l'objet du cas : au RETRAIT, `+0x98` est VIDE et `+0x60` porte l'effet.

    `RemoveEffectOperation$$Execute` n'appelle aucun ctor ; entre son `memset(0, 0x128)` et la copie
    publiee, aucune ecriture ne touche `+0x98`. Un gate `TriggeringEffectIs` cable sur un vecteur de
    retrait serait donc TOUJOURS faux cote natif -- c'est `CurrentAbilityIs` qu'il faut lire."""
    r = effect_trigger_channel_case()
    for site in EFC.SITES_REMOVE:
        ev60, ev98, st60, st98 = EFC.site(r, site)
        assert ev98 is None and st98 is None, (
            f"'{site}' voit +0x98 = (ev {ev98}, st {st98}) ; RemoveEffectOperation ne l'ecrit "
            f"JAMAIS -> le memset l'exige VIDE")
        assert (ev60, st60) == (EFC.EFFECT_TYPE, EFC.EFFECT_TYPE), (
            f"'{site}' voit +0x60 = (ev {ev60}, st {st60}) ; c'est CurrentAbilityIs qui porte "
            f"l'effet retire ({EFC.EFFECT_TYPE})")


def test_the_memset_overwrites_the_ambient_channels(effect_trigger_channel_case):
    """LA PORTEE : le memset natif ECRASE ce qu'une triggered englobante avait mis.

    Le port n'a que des canaux GLOBAUX ; sans ecrasement explicite, l'id de la triggered en cours
    resterait visible en `+0x60` pendant le vecteur d'effet, et `CurrentAbilityIs(<cette
    triggered>)` y serait VRAI cote port, FAUX cote natif. C'est la moitie du bug qui ne se voyait
    pas dans le payload."""
    r = effect_trigger_channel_case()
    for site in EFC.SITES_ADD:
        _, _, st60, st98 = EFC.site(r, site)
        assert (st60, st98) == (EFC.EFFECT_TYPE, EFC.EFFECT_TYPE), (
            f"'{site}' voit l'ambiant ({st60}, {st98}) ; le memset le remplace par l'effet "
            f"{EFC.EFFECT_TYPE} (ambiant arme = {EFC.AMBIENT_CURRENT}/{EFC.AMBIENT_TRIGGER})")


def test_both_channels_are_restored_after_the_vector(effect_trigger_channel_case):
    """PORTEE, suite : le vecteur ne fait fuir NI l'un NI l'autre.

    Le natif jette l'`AbilityEntities` de l'Operation avec elle ; le port, qui n'a que des canaux
    globaux, doit restaurer les deux a leur valeur d'avant."""
    r = effect_trigger_channel_case()
    assert r["final"] == (EFC.AMBIENT_CURRENT, EFC.AMBIENT_TRIGGER)


def test_the_remove_vectors_are_actually_emitted(effect_trigger_channel_case):
    """Le montage a bien EXERCE un retrait : sans stack retire, les deux vecteurs seraient partis a
    vide et les gardes ci-dessus ne prouveraient rien (un site absent leve deja dans `EFC.site`)."""
    r = effect_trigger_channel_case()
    assert r["removed"] >= 1, "aucun stack retire -- le montage n'a pas exerce la feuille RemoveEffect"


def test_the_probe_verdict_agrees(effect_trigger_channel_case):
    """Un seul foyer d'assertion : le verdict du probe dit la MEME chose que les gardes ci-dessus.
    Sans ce test, probe et suite peuvent diverger silencieusement."""
    ok, msg = EFC.verdict(effect_trigger_channel_case())
    assert ok, msg


def test_the_add_only_mode_agrees_too(effect_trigger_channel_case):
    """Le mode `add_only` (celui qui tourne AUSSI sur le code d'avant #306, ou les vecteurs de
    retrait n'existent pas) doit etre VERT sur le depot courant. C'est lui qui a donne le ROUGE de
    reference : `(None, 1065, 6161, 6262)` au lieu de `(1065, 1065, 1065, 1065)`."""
    ok, msg = EFC.verdict(effect_trigger_channel_case(add_only=True))
    assert ok, msg


@pytest.mark.parametrize("mutation", sorted(EFC.MUTATIONS))
def test_each_mutation_reddens_the_montage(effect_trigger_channel_case, mutation):
    """CONTRE-EPREUVES : chacune neutralise une moitie du fix et DOIT rougir.

    `legacy` = l'etat exact d'avant #306 (la pose n'ecrit que `+0x98` et ne touche pas l'ambiant, le
    retrait n'emet aucun vecteur) ; `symmetric` = le retrait ecrit `+0x98` comme la pose (la
    confusion que ce cas corrige) ; `noambient` = payload correct mais ambiant non ecrase ;
    `persist` = pas de restauration. Une garde qui ne rougit sur aucune mutation ne garde rien."""
    ok, msg = EFC.verdict(effect_trigger_channel_case(mutate=mutation))
    assert not ok, f"la mutation '{mutation}' n'a RIEN casse -- le montage ne discrimine pas"
    assert msg.startswith("ROUGE"), msg


def test_mutations_have_distinct_signatures(effect_trigger_channel_case):
    """ANTI-CONTRE-EPREUVE FOURRE-TOUT : les quatre mutations doivent rougir pour QUATRE raisons
    differentes. Si deux d'entre elles rendaient le meme message, l'une des deux ne testerait rien
    de propre et le montage serait plus faible qu'il n'en a l'air."""
    msgs = {m: EFC.verdict(effect_trigger_channel_case(mutate=m))[1] for m in EFC.MUTATIONS}
    assert len(set(msgs.values())) == len(EFC.MUTATIONS), f"signatures non distinctes : {msgs}"


def test_a_nested_pose_does_not_inherit_the_death_context():
    """GENERALISATION -- le regime le plus discriminant, et il n'etait couvert par AUCUN test.

    Une pose d'effet faite DANS le drain de mort (la forme d'`ActOfFaith` accumulate : un trigger
    de `On(1)` qui pose un effet) : l'ambiant d'entree y est `(None, killTrigger)`, le mirror du
    memset de `KillUnitOperation` (#301). Le natif y batit un `AbilityEntities` NEUF pour
    l'`AddEffectOperation` -> le vecteur d'effet publie `(effectType, effectType)` et n'herite RIEN
    du contexte de mort.

    ROUGE mesure sur `origin/master` : `On(61 = PreEffectAdded)` imbrique y voyait
    `(None, 1065, None, 6363)` -- soit le `killTrigger` du drain publie sous un evenement d'EFFET.
    Et l'inverse compte autant : le drain doit RETROUVER son contexte apres le vecteur."""
    ok, msg = EFC.verdict_nested(EFC.run_nested())
    assert ok, msg


def test_the_divergence_is_latent_and_says_why():
    """POURQUOI CE FIX NE CHANGE AUCUNE OBSERVABLE -- et le CLIQUET qui le rendra decisif.

    Compte RE-DERIVE du registre (jamais herite) : un SEUL trigger porte ecoute un vecteur d'effet
    (`TerrifyingCrescendoSuppressAbility` sur `On(61 = PreEffectAdded)`), et il lit `+0x98`, que ce fix ne touche pas.
    Les CINQ autres vecteurs d'effet n'ont AUCUN consommateur. La correction porte donc sur le CANAL
    seul : c'est exactement pourquoi elle etait muette et pourquoi la garde est cablee ici plutot
    que sur un observable de bataille.

    Ce test n'interdit pas d'ajouter un consommateur -- il rougit quand on en ajoute un sur un
    vecteur de RETRAIT, au moment precis ou le canal lu cesse d'etre indifferent : le porteur devra
    alors lire `CurrentAbilityIs` (`ev.triggering_ability`), jamais `TriggeringEffectIs`."""
    from engine.dsl.event_trigger_type import EventTriggerType
    c = EFC.consumers(verbose=False)
    add61 = c["by_event"][int(EventTriggerType.PreEffectAdded)]
    assert add61 == ["TerrifyingCrescendoSuppressAbility"], (
        f"consommateurs de On(61) = {add61} ; un nouvel entrant doit declarer quel canal il lit "
        f"(+0x60 CurrentAbilityIs / +0x98 TriggeringEffectIs) et mettre ce test a jour")
    for ev in (EventTriggerType.PreEffectRemoved, EventTriggerType.EffectRemoved,
               EventTriggerType.UnitBecameTargetable):
        got = c["by_event"][int(ev)]
        assert got == [], (
            f"On({int(ev)}) a maintenant un consommateur porte : {got}. C'est un vecteur de "
            f"RETRAIT -> il doit lire `ev.triggering_ability` (+0x60), car "
            f"RemoveEffectOperation laisse +0x98 VIDE (#306)")


def test_the_pose_consumer_still_reads_the_0x98_channel():
    """LE CONSOMMATEUR PORTE ne bouge pas. `TerrifyingCrescendoAbility` branche 2 porte
    `On(0x3d = 61 PreEffectAdded) & OwnerIsActor & TriggeringEffectIs(0x429 = Pinned)` : ce predicat
    prend le slot `DSLSelectors+0x90`, donc `+0x98`, donc `ev.triggering_effect`.

    Le fix #306 AJOUTE `+0x60` sans toucher `+0x98` : cette lecture-la reste EXACTE, et la garde le
    verifie sur le vrai `matches` de la classe portee."""
    from engine.runner.state import State
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.loki.terrifying_crescendo import (
        TerrifyingCrescendoSuppressAbility, PINNED)

    st = State()
    trig = TerrifyingCrescendoSuppressAbility(1)
    ok_ev = TriggerEvent(int(EventTriggerType.PreEffectAdded), 1, 2, ranged=False, profile=None,
                         triggering_ability=PINNED, triggering_effect=PINNED)
    assert trig.matches(st, ok_ev), "le gate TriggeringEffectIs(Pinned) ne voit plus le canal +0x98"
    # `+0x60` SEUL renseigne (la forme d'un vecteur de RETRAIT) -> le gate ne doit RIEN y voir.
    ko_ev = TriggerEvent(int(EventTriggerType.PreEffectAdded), 1, 2, ranged=False, profile=None,
                         triggering_ability=PINNED, triggering_effect=None)
    assert not trig.matches(st, ko_ev), (
        "le gate lit +0x60 : il verrait un declencheur la ou RemoveEffectOperation n'en publie aucun")
