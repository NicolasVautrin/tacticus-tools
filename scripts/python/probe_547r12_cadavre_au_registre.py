"""#547-r12 -- UN CADAVRE-AU-CHARGEMENT PORTEUR D'UNE `fire_on_death` ENTRE AU REGISTRE.

===================================================================================================
LE PARTAGE NATIF, RELU VERBATIM SUR `t6dpr4k06g`
===================================================================================================

Le natif separe ce que le port confondait -- le CACHE garde, la LECTURE trie :

  * `IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache$$AddEntity` n'a AUCUN gate de
    vivacite. Son corps entier aiguille sur le type d'entite (`IsEffect` -> `AddEffect`, sinon
    `TryGetComponent<TriggeredAbilityComponent>` -> `AddAbility`) ; ni `IsAlive`, ni HP, ni stats.
  * `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` trie A LA LECTURE :

        if (ability == null) throw;
        if (!ability.get_AllowForDeadOwner()) {                  // ITriggeredAbility slot 8
            if (IsUnit(owner) && !IsAlive(owner))    return 0; }
        if (IsUnit(owner) && IsTriggersDisabled(owner))          return 0;
        ...                                                      // puis les gates ATOMIQUES

Le port, lui, coupait AVANT le gate : `collect_triggered_abilities` ouvre sur
`if sc is None: continue`, et le `StatsComponent` n'est pose que depuis une ligne de
`combatSnapshot.units[]` -- capteur qui FILTRE `IsAlive`. Une entite chargee depuis
`decisionView.units[]` (qui CONSERVE les morts AVEC leurs effets) et absente du snapshot n'avait
donc AUCUNE triggered-ability inscrite, exemptee comprise.

CAS MOTIVANT -- `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAbility`
(`TriggeredAbilityType` 0x419 = 1049, passif du summon `adeptSmnGeminaeSuperia`), dont
`get_AllowForDeadOwner` rend VRAI (entree versionnee `metadata/allow_for_dead_owner.tsv`) :

    $$CreateTrigger = On(0x39 = PreDamageTaken) & <DSLTriggers+0x70 = YesTrigger>
        & ( IsAlive(Owner@<DSLSelectors+0x30>)
            | HasEffect(Owner@+0x30, 0x4d8 = 1240, onlyActive: 0, effectTarget: 6) )
        & AreEqual(Target@<DSLSelectors+0x60>, Parent(Owner@+0x30))
        & IsAdjacent(Owner@+0x30, Target@+0x60, 0)

La disjonction est ecrite EXPRES : une Geminae MORTE qui porte encore le marqueur 1240 absorbe
encore le coup destine a Celestine (son `Parent`). Sans inscription, Celestine encaisse des degats
que le natif lui epargne.

===================================================================================================
LES CINQ ETAGES
===================================================================================================

  `--step natif`         le decompile ci-dessus, cite (informationnel).
  `--step inscription`   le cadavre-Geminae entre au registre, ET la MORSURE : neutraliser le
                         correctif le fait ressortir. Un etage qui ne mord d'aucun cote serait
                         vert par vacuite.
  `--step observable`    ce que ca CHANGE : le `pending_damage` de Celestine est CONSOMME (elle ne
                         perd rien) avec le 1240, CONSERVE sans lui, et neutralise sans correctif.
  `--step ventilation`   L'ETAGE ADVERSARIAL. Les 23 autres porteurs `fire_on_death` etaient
                         ranges << regime divergent VIDE >> par une LECTURE DE CODE (#547-r11) que
                         rien n'exercait. Ce correctif les inscrit pour de vrai : on EXERCE donc
                         leur `matches` sur un cadavre-au-chargement, dans CINQ regimes, et on
                         exige qu'aucun ne tire dans les deux regimes ATTEIGNABLES -- ni ne LEVE
                         (une exception remonterait `evaluate_trigger_operation` et casserait le
                         dispatch : c'est le vrai risque de cette tranche).
  `--step preservation`  value-preserving : un etat SANS cadavre-au-chargement rend le registre
                         bit-a-bit identique avec et sans correctif.
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from engine.dsl.event_trigger_type import EventTriggerType                      # noqa: E402
from engine.entities.effects_state import EffectsState                          # noqa: E402
from engine.entities.stats import UnitStats                                     # noqa: E402
from engine.entities.unit_context import UnitContext                            # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,          # noqa: E402
                                      PendingDamage, PositionComponent,
                                      StatsComponent, TriggeredAbilityComponent,
                                      UnitComponent)
from engine.runner.operations.behaviour import BEHAVIOUR_TRAIT_TRIGGERS         # noqa: E402
from engine.runner.operations.triggers.base import (EffectTrigger,              # noqa: E402
                                                    TriggerEvent)
from engine.runner.operations.triggers.dispatch import core as CORE             # noqa: E402
from engine.runner.operations.triggers.dispatch import registry as R            # noqa: E402
from engine.runner.state import Entity, State                                   # noqa: E402

#: L'id d'ability que le publieur natif d'`On(0x39)` pose dans `AbilityEntities+0x98`. Toute
#: valeur non nulle suffit : le behaviour ne s'en sert que comme GATE (`attackAbility.HasValue`)
#: et comme NOM de la source du degat transfere. Ce n'est pas un ordinal d'enum -- c'est le canal.
_ABILITY_SOURCE_DU_COUP = 1234

CELESTINE, GEMINAE, ENNEMI = 1, 2, 3
MORT, ACTEUR, CIBLE = 7, 8, 9

#: `EffectType.Lifewards_Protecting` -- lu par son membre, pas par son ordinal.
from engine.entities.effect_type import EffectType                              # noqa: E402,E401

PROTECTING = EffectType.Lifewards_Protecting


# =================================================================================================
# MONTAGES
# =================================================================================================
def _pose_unite(st: State, eid: int, vid: str, col: int, *, alive: bool, team: int,
                stats: bool, parent_id=None) -> Entity:
    """Une unite du plateau. `stats=False` = CADAVRE-AU-CHARGEMENT : aucun `StatsComponent`, ce
    qui est exactement l'etat que produit `snapshot.load_state` pour une entite presente dans
    `decisionView.units[]` et absente de `combatSnapshot.units[]`."""
    e = Entity(eid)
    e.add_component(UnitComponent(visual_id=vid, alive=alive, parent_id=parent_id))
    e.add_component(OwnerComponent(team=team, player=10 + team))
    e.add_component(PositionComponent(col=col, row=4))
    e.add_component(HealthComponent(hp=500 if alive else 0, hp_max=500))
    e.add_component(TriggeredAbilityComponent())
    if stats:
        ctx = UnitContext.__new__(UnitContext)
        ctx.visual_id = vid
        ctx.traits = []
        ctx.traits_measured = True
        ctx.stats = UnitStats()
        e.add_component(StatsComponent(ctx))
    st.entities[eid] = e
    return e


def etat_geminae(*, geminae_morte: bool = True, porte_1240: bool = True,
                 geminae_sans_stats: bool = True) -> State:
    """Celestine + sa Geminae + un ennemi. La Geminae est le CADAVRE-AU-CHARGEMENT."""
    st = State()
    _pose_unite(st, CELESTINE, "adeptCelestine", 4, alive=True, team=1, stats=True)
    _pose_unite(st, GEMINAE, "adeptSmnGeminaeSuperia", 5, alive=not geminae_morte, team=1,
                stats=not geminae_sans_stats, parent_id=CELESTINE)
    _pose_unite(st, ENNEMI, "necroWarden", 6, alive=True, team=2, stats=True)
    effs = ({GEMINAE: [{"name": PROTECTING.name, "effectType": int(PROTECTING)}]}
            if porte_1240 else {})
    st.effects = EffectsState.seed(effs, {}, {}, {})
    return st


def _event_pre_damage() -> TriggerEvent:
    return TriggerEvent(EventTriggerType.PreDamageTaken, ENNEMI, CELESTINE, ranged=False,
                        profile="Physical", triggering_effect=_ABILITY_SOURCE_DU_COUP)


class _SansCorrectif:
    """Neutralise `_triggers_du_cadavre_au_chargement` -- le comportement d'AVANT #547-r12.

    C'est la MORSURE : un etage qui reste identique une fois le correctif neutralise ne prouve pas
    que c'est LUI qui agit."""

    def __enter__(self):
        self._vrai = CORE._triggers_du_cadavre_au_chargement
        CORE._triggers_du_cadavre_au_chargement = lambda *a, **k: []
        return self

    def __exit__(self, *exc):
        CORE._triggers_du_cadavre_au_chargement = self._vrai
        return False


# =================================================================================================
# ETAGES
# =================================================================================================
def step_natif() -> int:
    print("NATIF -- le partage CACHE / LECTURE, relu sur `t6dpr4k06g`")
    print("")
    for ligne in (__doc__ or "").split("\n")[3:46]:
        print("  %s" % ligne if ligne.strip() else "")
    return 0


def _noms(reg) -> list:
    return sorted("%s@%s" % (type(x).__name__, x.owner_id) for x in reg)


def step_inscription() -> int:
    print("INSCRIPTION -- le cadavre-Geminae porte-t-il `LifewardsAbility` ?")
    print("")
    st = etat_geminae()
    avec = _noms(CORE.collect_triggered_abilities(st))
    with _SansCorrectif():
        sans = _noms(CORE.collect_triggered_abilities(etat_geminae()))
    print("  AVEC correctif : %s" % avec)
    print("  SANS correctif : %s" % sans)
    print("")
    attendu = "LifewardsAbility@%d" % GEMINAE
    rc = 0
    if attendu not in avec:
        print("  ROUGE : %s absent du registre AVEC correctif" % attendu)
        rc = 1
    if attendu in sans:
        print("  ROUGE : %s DEJA present sans correctif -- l'etage ne mord pas" % attendu)
        rc = 1
    # La Geminae VIVANTE (donc porteuse d'un `StatsComponent` dans un etat reel) doit passer par la
    # branche ORDINAIRE : le correctif ne doit pas etre son chemin.
    vivante = _noms(CORE.collect_triggered_abilities(
        etat_geminae(geminae_morte=False, geminae_sans_stats=False)))
    if attendu not in vivante:
        print("  ROUGE : la Geminae VIVANTE perd son inscription ordinaire")
        rc = 1
    print("  Geminae VIVANTE (branche ordinaire) : %s" % vivante)
    print("")
    print("  VOIE : `UnitComponent.visual_id` -> gameconfig `passiveAbilities` = ['Lifewards'].")
    print("  C'est le REPLI que le port applique deja a toute unite dont le canal est muet.")
    return rc


def step_observable() -> int:
    print("OBSERVABLE -- le `pending_damage` de Celestine est-il CONSOMME ?")
    print("")
    lignes = []

    def _jouer(porte_1240: bool, correctif: bool):
        st = etat_geminae(porte_1240=porte_1240)
        hc = st.get_entity(CELESTINE).get_component(HealthComponent)
        hc.pending_damage = PendingDamage(profile="Physical", health=300, shield=0)
        if correctif:
            res = CORE.evaluate_trigger_operation(st, _event_pre_damage())
        else:
            with _SansCorrectif():
                res = CORE.evaluate_trigger_operation(st, _event_pre_damage())
        transfere = any(t.get("result") for r in res for t in (r.get("transfers") or []))
        return hc.pending_damage is None, transfere

    for correctif in (True, False):
        for porte in (True, False):
            consomme, transfere = _jouer(porte, correctif)
            lignes.append((correctif, porte, consomme, transfere))
            print("  correctif=%-5s  1240=%-5s  pending CONSOMME=%-5s  transfert=%s"
                  % (correctif, porte, consomme, transfere))
    print("")
    attendu = {(True, True): (True, True),      # le seul regime ou Celestine est epargnee
               (True, False): (False, False),   # marqueur retire -> la Geminae morte n'absorbe plus
               (False, True): (False, False),   # sans correctif : le port laisse passer
               (False, False): (False, False)}
    rc = 0
    for correctif, porte, consomme, transfere in lignes:
        if (consomme, transfere) != attendu[(correctif, porte)]:
            print("  ROUGE : correctif=%s 1240=%s -> (%s, %s), attendu %s"
                  % (correctif, porte, consomme, transfere, attendu[(correctif, porte)]))
            rc = 1
    if rc == 0:
        print("  Les QUATRE cellules sont conformes. Celestine n'est epargnee QUE dans la cellule")
        print("  (correctif, 1240) -- c'est la mecanique du 2e conjoint natif, et c'est le")
        print("  correctif qui la rend atteignable.")
    return rc


# -------------------------------------------------------------------------------------------------
# VENTILATION ADVERSARIALE
# -------------------------------------------------------------------------------------------------
#: Les CINQ regimes. Les deux premiers sont ATTEIGNABLES pour un cadavre-au-chargement et sont donc
#: BLOQUANTS ; les trois autres sont imprimes en INVENTAIRE, avec la raison de leur inatteignabilite.
#:
#:   R1a / R1b : le cadavre n'est NI l'acteur NI la cible NI le mourant -- c'est le seul role qu'il
#:               puisse tenir. R1b l'enrichit au maximum (parent = la cible, adjacent, porteur du
#:               1240) pour qu'une classe qui PEUT matcher matche : un R1 pauvre serait vert par
#:               pauvrete du montage, pas par propriete du port.
#:   R2 (cible) : `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`
#:               est porte (#429-r1) ; le virtuel slot 0x11 `CanContinueOnDeadTarget` n'a AUCUN
#:               override et le bit 38 `AllowDeadTarget` n'a qu'un porteur, qui vise une TUILE.
#:   R3 (acteur) : un cadavre-au-chargement n'entre pas dans `toActivate`
#:               (`VerifyUnitsTurnFinishedOperation.verify_unit_turn_ended` rend `reason: dead`).
#:   R4 (mourant) : sa mort a eu lieu AVANT la capture ; l'evenement ne se republie pas.
REGIMES_ATTEIGNABLES = ("R1a-tiers-minimal", "R1b-tiers-enrichi")
REGIMES_INVENTAIRE = ("R2-cadavre-CIBLE", "R3-cadavre-ACTEUR", "R4-cadavre-MOURANT")


def _etat_ventilation(regime: str, vid_mort: str):
    st = State()
    enrichi = regime == "R1b-tiers-enrichi"
    _pose_unite(st, MORT, vid_mort, 4, alive=False, team=1, stats=False,
                parent_id=CIBLE if enrichi else None)
    _pose_unite(st, ACTEUR, "necroWarden", 5, alive=True, team=2, stats=True)
    _pose_unite(st, CIBLE, "ultraTerminator", 3, alive=True, team=1, stats=True)
    effs = ({MORT: [{"name": PROTECTING.name, "effectType": int(PROTECTING)}]}
            if enrichi else {})
    st.effects = EffectsState.seed(effs, {}, {}, {})
    return st


def _event_ventilation(regime: str, evid: int) -> TriggerEvent:
    acteur, cible, mourant = ACTEUR, CIBLE, ACTEUR
    if regime == "R2-cadavre-CIBLE":
        cible = MORT
    elif regime == "R3-cadavre-ACTEUR":
        acteur = MORT
    elif regime == "R4-cadavre-MOURANT":
        mourant = MORT
    return TriggerEvent(evid, acteur, cible, ranged=False, profile="Physical",
                        killer_id=ACTEUR, dying_id=mourant, player_id=12,
                        triggering_effect=_ABILITY_SOURCE_DU_COUP,
                        ability_type=_ABILITY_SOURCE_DU_COUP)


def porteurs_ability() -> dict:
    """{classe: (voie, cle)} -- les porteurs `fire_on_death` de face ABILITY, DERIVES des six
    tables de registration, jamais recopies (une liste ecrite derive sous la citation : c'est
    exactement la faute que `_owner_gate_applies` documente pour les quatre `EffectTrigger`)."""
    vues: dict = {}
    tables = {"TRAIT": R.TRAIT_TRIGGERS, "BEHAVIOUR_TRAIT": BEHAVIOUR_TRAIT_TRIGGERS,
              "PASSIVE": R.ABILITY_TRIGGERS, "ACTIVE_DERIVED": R.ACTIVE_ABILITY_TRIGGERS,
              "ACTIVE_HELPER": R.PASSIVE_HELPER_ABILITY_TRIGGERS,
              "RELIC": R.RELIC_ABILITY_TRIGGERS}
    for voie, table in tables.items():
        for cle, classes in table.items():
            for c in classes:
                if getattr(c, "fire_on_death", False) and not issubclass(c, EffectTrigger):
                    vues.setdefault(c, (voie, cle))
    return vues


def _events_de(cls) -> list:
    evs = []
    un = getattr(cls, "event_id", None)
    if un is not None:
        evs.append(int(un))
    evs.extend(int(x) for x in (getattr(cls, "event_ids", None) or []))
    return sorted(set(evs))


def ventiler() -> list:
    """[(classe, voie, regime, event, verdict)] -- `verdict` in {ecarte, MATCH, LEVE ...}."""
    out = []
    for cls, (voie, _cle) in sorted(porteurs_ability().items(), key=lambda kv: kv[0].__name__):
        vid = "adeptSmnGeminaeSuperia" if cls.__name__ == "LifewardsAbility" else "necroWarden"
        for regime in REGIMES_ATTEIGNABLES + REGIMES_INVENTAIRE:
            for evid in _events_de(cls):
                st = _etat_ventilation(regime, vid)
                try:
                    verdict = "MATCH" if cls(MORT).matches(st, _event_ventilation(regime, evid)) \
                        else "ecarte"
                except Exception as ex:                                          # noqa: BLE001
                    verdict = "LEVE %s: %s" % (type(ex).__name__, ex)
                out.append((cls.__name__, voie, regime, evid, verdict))
    return out


def step_ventilation() -> int:
    rows = ventiler()
    print("VENTILATION ADVERSARIALE -- les %d porteurs `fire_on_death` de face ABILITY, EXERCES"
          % len({r[0] for r in rows}))
    print("")
    rc = 0
    leves = [r for r in rows if r[4].startswith("LEVE")]
    if leves:
        rc = 1
        print("  LEVENT (une exception remonterait `evaluate_trigger_operation`) :")
        for r in leves:
            print("      %-46s %-18s ev=%-3d %s" % (r[0], r[2], r[3], r[4]))
        print("")
    for regime in REGIMES_ATTEIGNABLES + REGIMES_INVENTAIRE:
        m = [r for r in rows if r[2] == regime and r[4] == "MATCH"]
        bloquant = regime in REGIMES_ATTEIGNABLES
        print("  %-18s %-12s MATCH : %d" % (regime, "BLOQUANT" if bloquant else "inventaire",
                                            len(m)))
        for r in m:
            print("      %-46s %-14s ev=%d" % (r[0], r[1], r[3]))
    print("")
    # Le TEMOIN NON VIDE : sans lui, cet etage serait vert par vacuite (un `matches` qui rendrait
    # toujours False le rendrait vert aussi). Lifewards DOIT tirer dans R1b, qui EST son regime.
    temoin = [r for r in rows
              if r[0] == "LifewardsAbility" and r[2] == "R1b-tiers-enrichi" and r[4] == "MATCH"]
    if not temoin:
        print("  ROUGE : le TEMOIN est vide -- `LifewardsAbility` ne tire pas dans R1b, donc cet")
        print("  etage ne discrimine rien et son vert ne vaudrait rien.")
        rc = 1
    else:
        print("  TEMOIN NON VIDE : `LifewardsAbility` TIRE dans R1b (son propre regime).")
    autres = [r for r in rows if r[2] in REGIMES_ATTEIGNABLES and r[4] == "MATCH"
              and r[0] != "LifewardsAbility"]
    if autres:
        print("  ROUGE : un porteur AUTRE que Lifewards tire dans un regime ATTEIGNABLE --")
        print("  le tri << regime divergent VIDE >> de #547-r11 est FAUX pour lui.")
        rc = 1
    if [r for r in rows if r[0] == "LifewardsAbility" and r[2] == "R1a-tiers-minimal"
            and r[4] == "MATCH"]:
        print("  ROUGE : Lifewards tire meme SANS son montage (parent + 1240 + adjacence) --")
        print("  le trigger ne discrimine pas ce que le decompile lui fait discriminer.")
        rc = 1
    return rc


def step_preservation() -> int:
    """Value-preserving : le correctif ne touche QUE la branche `sc is None`."""
    print("PRESERVATION -- un etat SANS cadavre-au-chargement est-il inchange ?")
    print("")
    rc = 0
    for nom, fabrique in (("tous vivants", lambda: etat_geminae(geminae_morte=False,
                                                                geminae_sans_stats=False)),
                          ("morte AVEC stats (morte DU RUN)",
                           lambda: etat_geminae(geminae_morte=True, geminae_sans_stats=False))):
        avec = _noms(CORE.collect_triggered_abilities(fabrique()))
        with _SansCorrectif():
            sans = _noms(CORE.collect_triggered_abilities(fabrique()))
        egal = avec == sans
        print("  %-34s identique=%-5s  %s" % (nom, egal, avec))
        if not egal:
            print("      ROUGE : AVEC=%s  SANS=%s" % (avec, sans))
            rc = 1
    print("")
    print("  Le mort DU RUN garde son `StatsComponent` -- il passait DEJA par la branche")
    print("  ordinaire, et le correctif ne le voit jamais.")
    return rc


def step_amplitude() -> int:
    """CE QUE LE CORRECTIF NE PEUT PAS FERMER, ET LA MESURE QUI LE DIT (#547-r13).

    La fiche #547-r12 promettait un observable : << Celestine encaisse des degats que le natif lui
    epargne >>. Elle l'appuyait sur << `decisionView.units[]` conserve les morts AVEC leurs effets >>.
    **LA MOITIE DE CETTE PREMISSE EST FAUSSE, ET C'EST MESURE EN LIVE** (build `t6dpr4k06g`,
    runners 638 et 669, board MC1_67) :

      * les morts SONT conserves dans `decisionView.units[]` -- vrai, et c'est bien ce qui produit
        une entite sans `StatsComponent` (`combatSnapshot` ne les enumere pas : entityIds mesures
        `[77, 79, 81]` pour 4 unites en vue) ;
      * mais ils n'y portent **AUCUN effet**, y compris sous `includeInactive: true` -- le canal qui
        publie justement les effets poses-mais-INACTIFS. Mesure sur TROIS cadavres
        (`adeptSmnGeminaeSuperia` eid 95 au runner 638 ; eid 104 et 110 au runner 669) : `effects=[]`
        dans les deux modes. Le natif RETIRE les effets a la mort --
        `IdunBattle.Operations.KillUnitOperation$$Execute` appelle TROIS fois
        `...$$RemoveEffects(killed, step)` avec `step` = 0, 1, 2
        (`IdunBattle.Operations.KillUnitStep` = PreUnitRemove / AfterUnitRemove / AfterDeathTrigger).

    CONSEQUENCE, et c'est le verdict honnete de cette tranche : sur un etat issu d'une CAPTURE, les
    DEUX membres de la disjonction de `LifewardsAbility` sont faux pour un cadavre-au-chargement --
    `IsAlive(Owner)` par construction, `HasEffect(Owner, 1240)` parce que le marqueur n'est pas
    seede. Le correctif ferme donc un ecart de FIDELITE (le port inscrit desormais ce que le natif
    garde, et le tri retombe dans `matches`, la ou le natif le met) dont le regime OBSERVABLE via
    capture est VIDE. Ce qui reste ouvert est un ecart de SEEDING, pas de dispatch : residu #547-r13.

    OU VIT LE VRAI REGIME de la disjonction native -- il est INTRA-RESOLUTION, et le port le couvre
    DEJA : `IdunBattle.Entities.UnitExtensions$$IsAlive` est LU, il rend
    `!UnitFlagsComponent.Has(6) && <presente sur le plateau> && HealthComponent$$IsAlive()`. Une
    Geminae tombee a 0 PV est donc `IsAlive == false` AVANT que `KillUnitOperation` ne retire ses
    effets : elle porte encore 1240 et absorbe les coups suivants de la MEME resolution, jusqu'a ce
    que `LifewardsProtectingRemove` (`On(0x9 = Attack)`) le retire. Dans ce regime l'entite a ete
    SPAWNEE dans le run, donc elle a son `StatsComponent` et etait deja au registre."""
    print("AMPLITUDE -- ce que le correctif ferme, et ce qu'il ne peut PAS fermer")
    print("")
    rc = 0
    # Le cadavre REELLEMENT produit par `load_state` : ni stats, NI EFFETS.
    st = etat_geminae(porte_1240=False)
    inscrit = [x for x in CORE.collect_triggered_abilities(st)
               if type(x).__name__ == "LifewardsAbility"]
    matche = bool(inscrit) and inscrit[0].matches(st, _event_pre_damage())
    print("  cadavre TEL QUE `load_state` le produit (0 effet) : inscrit=%s  matches=%s"
          % (bool(inscrit), matche))
    if not inscrit:
        print("  ROUGE : le correctif ne l'inscrit meme pas")
        rc = 1
    if matche:
        print("  ROUGE : il MATCHE sans 1240 -- la disjonction ne discrimine plus rien")
        rc = 1
    # Le meme cadavre AVEC le marqueur (montage synthetique) : le tri retombe dans `matches`.
    st2 = etat_geminae(porte_1240=True)
    ins2 = [x for x in CORE.collect_triggered_abilities(st2)
            if type(x).__name__ == "LifewardsAbility"]
    m2 = bool(ins2) and ins2[0].matches(st2, _event_pre_damage())
    print("  meme cadavre AVEC 1240 (montage synthetique)     : inscrit=%s  matches=%s"
          % (bool(ins2), m2))
    if not m2:
        print("  ROUGE : le TEMOIN est vide -- l'etage ne discriminerait rien")
        rc = 1
    print("")
    for ligne in (step_amplitude.__doc__ or "").split("\n")[2:]:
        s = ligne.rstrip()
        print("  %s" % s.strip() if s.strip() else "")
    return rc


STEPS = {"natif": step_natif, "inscription": step_inscription, "observable": step_observable,
         "ventilation": step_ventilation, "preservation": step_preservation,
         "amplitude": step_amplitude}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", choices=sorted(STEPS) + ["all"], default="all")
    a = ap.parse_args()
    noms = sorted(STEPS) if a.step == "all" else [a.step]
    rc = 0
    for n in noms:
        print("=" * 99)
        print("STEP %s" % n)
        print("=" * 99)
        rc |= STEPS[n]()
        print("")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
