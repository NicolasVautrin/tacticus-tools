"""#287-r4 -- MESURE du porteur que `turnflow._has_valid_targets` passe au gate de ciblage.

CE QUE CE PROBE MESURE. La cascade `abilities/targeting.get_invalid_target_reason` consomme DEUX
membres sur son argument `ability` : le masque `TARGETING_OPTIONS`, et -- sous le bit
`TargetingRule.TargetMatchesDynamicRule` -- la METHODE `get_dynamic_invalid_target_reason`. Le
second n'est atteignable que sur une INSTANCE. Ce probe recense les `ActiveAbilityType` dont le
masque EFFECTIF porte ce bit, et confronte, id par id, le porteur reellement construit.

POURQUOI CE BIT, ET PAS UNE AUTRE PORTE. Relue a l'octet sur le build courant, la surcharge
**7 arguments** de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` -- celle que
`IdunBattle.Core.Services.TargetingQuery$$GetValidTargets` appelle, et que le port nomme
`apply_self_cast_switch=False` -- invoque le delegue `options+0x38` SANS GARDE :

    if ((options.Rules & 2) != 0) {              // TargetMatchesDynamicRule
        d = options.<+0x38>;                     // pose par `AActiveAbility$$.ctor` (vtable +0x480)
        if (d == null) <NullReferenceException>; // un delegue NUL leve -- il ne degrade pas
        rule = d.Invoke(caster, casterTiles, target, targetTiles);
        if (rule != 0) return GenericBrokenTargetingRule(rule);
    }

entre `TargetIsNotAdjacentToEnemy` (bit 42) et `TargetIsCasterOrEnemy` (bit 57). « Filtre statique
pur » ne qualifie donc QUE l'absence de l'aiguillage self-cast et du volet caster -- tous deux dans
les surcharges 5 arguments, en AMONT. La regle dynamique, elle, est bien dans la 7 arguments : le
port a un bug de TYPAGE, pas de CADRAGE.

TROIS MESURES, toutes OFFLINE (aucun runner, aucune session Frida) :
  1. RECENSEMENT -- les ids dont le masque effectif (`targeting_options_for`) porte le bit,
     ventiles par VOIE : classe du registre `ABILITY_CLASSES` / porteur « non porte ».
  2. APPEL -- `_has_valid_targets` sur un etat minimal, et l'exception rendue s'il y en a une.
  3. PORTEUR -- l'objet reellement passe a la cascade est intercepte, et l'on regarde si sa
     `get_dynamic_invalid_target_reason` est une methode LIEE. Cette mesure-la est EXHAUSTIVE :
     elle ne depend pas de la profondeur que la cascade atteint sur l'etat minimal.

Usage :
    python scripts/python/probe_287r4_targeting_needs_instance.py
    python scripts/python/probe_287r4_targeting_needs_instance.py --ids       # detail par id
ASCII only ; exit 0 = aucun porteur fautif.
"""
from __future__ import annotations

import argparse
import collections
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import engine.runner.operations.turnflow as TF                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                 # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                       # noqa: E402
from engine.runner.abilities.targeting import (                                   # noqa: E402
    TARGETING_OPTIONS_UNPORTED, targeting_options_for,
)
from engine.runner.abilities.targeting_rule import TargetingRule as TR            # noqa: E402
from engine.runner.state import State                                             # noqa: E402


def _nom(aid: int) -> str:
    """Le membre d'enum, jamais l'ordinal nu (regle du depot)."""
    try:
        return ActiveAbilityType(int(aid)).name
    except ValueError:
        return "<hors ActiveAbilityType>"


def ids_portant_le_bit() -> list:
    """Les `ActiveAbilityType` dont le masque EFFECTIF porte `TargetMatchesDynamicRule`.

    Le substrat est `targeting_options_for` -- le FOYER UNIQUE du masque, qui consulte
    `ABILITY_CLASSES[aid].TARGETING_OPTIONS` puis `TARGETING_OPTIONS_UNPORTED`. On ne recense donc
    pas « les classes qui surchargent la regle dynamique » (un sous-ensemble strict) : le bit se lit
    sur le MASQUE, et c'est lui seul qui fait entrer la cascade dans la branche fautive -- meme
    lorsque la sous-classe se contente du defaut herite d'`ActiveAbility`."""
    out = []
    for aid in sorted(set(ABILITY_CLASSES) | set(TARGETING_OPTIONS_UNPORTED)):
        opts = targeting_options_for(aid)
        if opts is not None and opts.has(TR.TargetMatchesDynamicRule):
            out.append(int(aid))
    return out


def voie(aid: int) -> str:
    """Par ou `_has_valid_targets` fabrique son porteur : `classe` ou `non_porte`."""
    klass = ABILITY_CLASSES.get(int(aid))
    if klass is not None and getattr(klass, "TARGETING_OPTIONS", None) is not None:
        return "classe"
    return "non_porte"


def _etat_minimal() -> State:
    """Deux entites NUES. Volontairement degenere : la cascade y degrade en permissif a chaque
    regle qu'elle ne sait pas mesurer, ce qui la fait DESCENDRE jusqu'au bit dynamique. C'est le
    regime le plus court qui atteigne le site fautif -- aucun board, aucun composant, aucun RPC."""
    st = State()
    st.add_entity(1)
    st.add_entity(2)
    return st


class sans_volet_caster:
    """Neutralise le VOLET CASTER de `_has_valid_targets` le temps d'une mesure.

    POURQUOI, ET POURQUOI CE N'EST PAS UNE TRICHE. Sur l'etat minimal le caster n'a AUCUNE tuile,
    donc `get_invalid_caster_reason` rend legitimement `TargetingRule.AllowNullCasterTile` (la clause
    tuile-nulle de `TargetingQuery$$GetInvalidCasterReason`, portee par #366-r1) pour 39 des 47 ids
    a classe portee. `_has_valid_targets` sortirait alors AVANT la cascade, et les mesures 2 et 3 --
    qui portent sur le PORTEUR, pas sur le volet caster -- deviendraient vraies par VACUITE : un vert
    qui ne visite rien. On isole donc l'etage mesure, et le volet caster a son propre temoin
    (`temoin_volet_caster`), avec un substrat ou il DISCRIMINE.

    Sur un arbre ou `turnflow` n'importe pas encore ce nom, le remplacement est un NO-OP et la
    restauration retire l'attribut : la mesure reste jouable des deux cotes du correctif."""

    def __enter__(self):
        self._avait = hasattr(TF, "get_invalid_caster_reason")
        self._origine = getattr(TF, "get_invalid_caster_reason", None)
        TF.get_invalid_caster_reason = lambda state, caster_id, ability: 0
        return self

    def __exit__(self, *exc):
        if self._avait:
            TF.get_invalid_caster_reason = self._origine
        else:
            del TF.get_invalid_caster_reason
        return False


def mesurer_appel(ids: list) -> dict:
    """MESURE 2 -- `_has_valid_targets` par id ; rend {aid: None | "<Type>: <message>"}."""
    st = _etat_minimal()
    out = {}
    with sans_volet_caster():
        for aid in ids:
            try:
                TF._has_valid_targets(st, 1, aid)
                out[aid] = None
            except Exception as exc:                               # noqa: BLE001 -- c'est la mesure
                out[aid] = "%s: %s" % (type(exc).__name__, exc)
    return out


def mesurer_porteur(ids: list) -> dict:
    """MESURE 3 -- le porteur REELLEMENT passe a la cascade, id par id.

    On substitue `get_invalid_target_reason` DANS le module `turnflow` (c'est le nom qu'il a
    importe) par un espion qui capture son argument `ability` et rend 0. L'espion court-circuite la
    cascade : la mesure est donc INDEPENDANTE de la profondeur que l'etat minimal permet
    d'atteindre, et couvre les ids que la mesure 2 ne pourrait pas visiter.

    Rend {aid: (nom du type porteur, "liee" | "non_liee" | "absente", classe_nommee)}."""
    st = _etat_minimal()
    captures: list = []

    def espion(state, caster_id, target_id, ability, **kwargs):
        captures.append(ability)
        return 0

    out = {}
    origine = TF.get_invalid_target_reason
    TF.get_invalid_target_reason = espion
    try:
        with sans_volet_caster():
            for aid in ids:
                captures.clear()
                TF._has_valid_targets(st, 1, aid)
                if not captures:
                    out[aid] = ("<aucun porteur construit>", "absente", False)
                    continue
                ab = captures[0]
                attr = getattr(ab, "get_dynamic_invalid_target_reason", None)
                if attr is None:
                    etat = "absente"
                elif inspect.ismethod(attr):
                    etat = "liee"
                else:
                    etat = "non_liee"
                nom = ab.__name__ if isinstance(ab, type) else type(ab).__name__
                out[aid] = (nom, etat, est_instance_de_classe_nommee(ab))
    finally:
        TF.get_invalid_target_reason = origine
    return out


def temoin_volet_caster() -> dict:
    """LE VOLET CASTER, mesure par un couple de masques qui ne different QUE d'un bit.

    `TargetingQuery$$GetValidTargets` -- la fonction dont `_has_valid_targets` est le mirror --
    ouvre par `GetInvalidCasterReason` et rend `ValidTargets.Empty` si le caster est refuse, AVANT
    toute enumeration. Ses QUATRE surcharges convergent vers ce corps.

    SUBSTRAT DISCRIMINANT, et 100 % offline : sur l'etat minimal le caster n'a AUCUNE tuile, donc la
    clause tuile-nulle du volet caster rend `AllowNullCasterTile` -- sauf si le masque POSE ce bit,
    qui la desarme (`(rules & AllowNullCasterTile) == 0 && ...`). Deux masques a un bit d'ecart
    donnent donc deux verdicts opposes, sans board ni RPC.

    MESURE LIVE qui a impose cet etage (C1_02 / seed 28704, `orksWarboss` apres un pas) : natif
    `abilityReason.casterReason = CasterHasNotMoved`, `UnitFlag.NoActionAvailable` POSE ; le port
    sans cet etage trouvait `Waaagh` castable et laissait l'unite jouable."""
    from engine.runner.abilities.base import ActiveAbility
    from engine.runner.abilities.targeting import TargetingOptions

    aid = max(set(ABILITY_CLASSES) | set(TARGETING_OPTIONS_UNPORTED)) + 3
    rules = int(TR.TargetMatchesDynamicRule)

    class _CasterRefuse(ActiveAbility):
        TARGETING_OPTIONS = TargetingOptions(rules=rules)

    class _CasterTolere(ActiveAbility):
        TARGETING_OPTIONS = TargetingOptions(rules=rules | int(TR.AllowNullCasterTile))

    out = {}
    for etiquette, klass in (("refuse", _CasterRefuse), ("tolere", _CasterTolere)):
        ABILITY_CLASSES[aid] = klass
        try:
            out[etiquette] = TF._has_valid_targets(_etat_minimal(), 1, aid)
        except Exception as exc:                                   # noqa: BLE001 -- c'est la mesure
            out[etiquette] = "%s: %s" % (type(exc).__name__, exc)
        finally:
            del ABILITY_CLASSES[aid]
    return out


def temoin_non_degenere() -> dict:
    """LE TEMOIN. Sans lui, « aucune exception » se contenterait d'un `try/except` -- ou du RETRAIT
    pur et simple de l'appel a la regle dynamique, qui rendrait le probe vert en supprimant la
    mecanique qu'il pretend garder.

    On inscrit dans `ABILITY_CLASSES` une classe TEMOIN dont la surcharge REFUSE toute cible, sous
    un masque qui ne porte QUE `TargetMatchesDynamicRule`, et l'on exige que `_has_valid_targets`
    bascule de `True` (une cible passe) a `False` (aucune). On enregistre aussi les arguments recus,
    pour que l'ORDRE `(state, caster_id, target_id)` soit mesure et non supprime."""
    from engine.runner.abilities.base import ActiveAbility
    from engine.runner.abilities.targeting import TargetingOptions

    recu: list = []
    aid_temoin = max(set(ABILITY_CLASSES) | set(TARGETING_OPTIONS_UNPORTED)) + 1

    class _TemoinPermissif(ActiveAbility):
        TARGETING_OPTIONS = TargetingOptions(rules=int(TR.TargetMatchesDynamicRule))

    class _TemoinRefus(ActiveAbility):
        TARGETING_OPTIONS = TargetingOptions(rules=int(TR.TargetMatchesDynamicRule))

        def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
            recu.append((state, caster_id, target_id))
            return int(TR.TargetMatchesDynamicRule)

    st = _etat_minimal()
    out = {}
    for etiquette, klass in (("permissif", _TemoinPermissif), ("refus", _TemoinRefus)):
        ABILITY_CLASSES[aid_temoin] = klass
        try:
            # Volet caster ISOLE : ce temoin mesure la REGLE DYNAMIQUE. Le caster de l'etat minimal
            # n'a aucune tuile, donc sans cette isolation le volet sortirait en tete et les deux
            # bras rendraient `False` -- une bascule qui ne discriminerait plus rien.
            with sans_volet_caster():
                out[etiquette] = TF._has_valid_targets(st, 1, aid_temoin)
        except Exception as exc:                                   # noqa: BLE001 -- c'est la mesure
            # Sur un arbre FAUTIF le temoin leve avant de rendre un verdict : on RAPPORTE
            # l'exception au lieu de la propager, pour que la sortie reste lisible des deux cotes.
            out[etiquette] = "%s: %s" % (type(exc).__name__, exc)
        finally:
            del ABILITY_CLASSES[aid_temoin]
    out["args"] = list(recu)
    return out


def est_instance_de_classe_nommee(obj) -> bool:
    """`obj` est-il une INSTANCE dont le type est une classe NOMMEE de son module ?

    DEUX refus, et les deux sont des fautes distinctes vues sur `master` :
      * `isinstance(obj, type)` -- le porteur EST une classe (jamais instanciee). C'est la face qui
        rend la methode NON LIEE ;
      * un type fabrique au site (`type("_X", (), {...})` dans le corps d'une fonction) n'est
        reference par AUCUN attribut de son module : `getattr(module, "_X")` echoue, la ou une
        classe ecrite au niveau module s'y resout et est IDENTIQUE a l'objet.

    Ce critere ne cite aucun symbole neuf : il se joue des DEUX cotes du correctif, ce qui permet
    d'OBSERVER la bascule au lieu de rougir sur un `ImportError` -- lequel ne prouverait rien de la
    mecanique gardee."""
    if isinstance(obj, type):
        return False
    t = type(obj)
    module = sys.modules.get(t.__module__)
    return module is not None and getattr(module, t.__name__, None) is t


def temoin_non_porte() -> dict:
    """Le pendant de la voie « non portee » : un masque LU sans classe de behaviour. Le porteur doit
    etre une classe NOMMEE, et sa regle-delegue doit etre APPELABLE (elle rend 0 -- la degradation
    permissive NOMMEE, le port ne pouvant pas evaluer un corps qu'il n'a pas)."""
    from engine.runner.abilities.targeting import TargetingOptions

    aid_temoin = max(set(ABILITY_CLASSES) | set(TARGETING_OPTIONS_UNPORTED)) + 2
    TARGETING_OPTIONS_UNPORTED[aid_temoin] = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule))
    try:
        porteur = mesurer_porteur([aid_temoin])[aid_temoin]
        appel = mesurer_appel([aid_temoin])[aid_temoin]
        return {"porteur": porteur, "exception": appel,
                "est_la_classe_nommee": porteur[2]}
    finally:
        del TARGETING_OPTIONS_UNPORTED[aid_temoin]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", action="store_true", help="detail id par id")
    args = ap.parse_args()

    ids = ids_portant_le_bit()
    par_voie = collections.Counter(voie(a) for a in ids)
    print("[287-r4] RECENSEMENT -- masque effectif portant TargetMatchesDynamicRule")
    print("  ids                 : %d" % len(ids))
    print("  voie classe portee  : %d" % par_voie["classe"])
    print("  voie non portee     : %d" % par_voie["non_porte"])
    if not ids:
        print("  ECHEC : recensement VIDE -- un probe qui ne visite rien ne peut rien mesurer.")
        return 1

    appels = mesurer_appel(ids)
    fautes = {a: m for a, m in appels.items() if m is not None}
    par_type = collections.Counter(m.split(":")[0] for m in fautes.values())
    print("[287-r4] APPEL -- `_has_valid_targets` sur un etat minimal")
    print("  sans exception      : %d / %d" % (len(ids) - len(fautes), len(ids)))
    for t, n in sorted(par_type.items()):
        print("    %-16s %d" % (t, n))

    porteurs = mesurer_porteur(ids)
    mauvais = {a: v for a, v in porteurs.items() if v[1] != "liee" or not v[2]}
    types = collections.Counter(v[0] for v in porteurs.values())
    anonymes = sum(1 for v in porteurs.values() if not v[2])
    print("[287-r4] PORTEUR -- objet reellement passe a la cascade")
    print("  regle dynamique LIEE : %d / %d" % (
        sum(1 for v in porteurs.values() if v[1] == "liee"), len(ids)))
    print("  type fabrique au site: %d (attendu 0 -- une classe NOMMEE est requise)" % anonymes)
    for t, n in sorted(types.items()):
        print("    %-28s %d" % (t, n))

    tem = temoin_non_degenere()
    print("[287-r4] TEMOIN NON DEGENERE -- la regle dynamique est-elle CONSULTEE ?")
    print("  surcharge permissive -> _has_valid_targets = %s (attendu True)" % tem["permissif"])
    print("  surcharge REFUS      -> _has_valid_targets = %s (attendu False)" % tem["refus"])
    print("  arguments recus      : %d appel(s), forme %s"
          % (len(tem["args"]), "(state, caster_id, target_id)" if tem["args"] else "<aucune>"))
    tem_np = temoin_non_porte()
    print("  voie non portee      -> porteur %s, exception %s"
          % (tem_np["porteur"], tem_np["exception"]))
    tem_c = temoin_volet_caster()
    print("[287-r4] VOLET CASTER -- consulte EN TETE, comme `GetValidTargets` ?")
    print("  caster REFUSE (tuile nulle)      -> _has_valid_targets = %s (attendu False)"
          % tem_c["refuse"])
    print("  meme masque + AllowNullCasterTile -> _has_valid_targets = %s (attendu True)"
          % tem_c["tolere"])

    if args.ids:
        print("[287-r4] DETAIL")
        for a in ids:
            print("  %-6d %-34s %-10s %-28s %-8s %s"
                  % (a, _nom(a), voie(a), porteurs[a][0], porteurs[a][1], appels[a] or "ok"))

    ok = (not fautes and not mauvais
          and tem["permissif"] is True and tem["refus"] is False and tem["args"]
          and tem_np["est_la_classe_nommee"] and tem_np["exception"] is None
          and tem_c["refuse"] is False and tem_c["tolere"] is True)
    print("[287-r4] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    if not ok and (fautes or mauvais):
        for a in sorted(set(fautes) | set(mauvais))[:10]:
            print("  FAUTE %-6d %-34s %s" % (a, _nom(a), appels.get(a) or porteurs.get(a)))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
