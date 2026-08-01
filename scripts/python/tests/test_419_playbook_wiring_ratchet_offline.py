"""#419 -- CLIQUET du patron « playbook PORTE mais NON CABLE ».

Le bug fondateur (#415, `SuppressiveFire` 1044) tenait en DEUX bouts manquants : le playbook lui-meme
ET son entree de dispatch. Un playbook porte mais jamais itere est INERTE -- il ne leve rien, ne
casse aucun test, et vaut zero point pour tous ses porteurs. Rien dans le depot ne le signalait.

Ce cliquet fait rougir les DEUX fautes qui rouvrent le patron, mesurees sur la table de symboles
VERSIONNEE (aucun RPC, aucun runner) :

  1. **PORTE + NON CABLE** -- une entree de registre dont l'ability n'a AUCUN porteur, ni par la voie
     dispatchee offline (`kit_triggered_ability_ids` = passiveAbilities + traits), ni par une voie
     que le canal live `unitAbilityStates` rattrape (relique / mythique / item, #323). Personne ne
     l'appellera jamais.
  2. **PORTE ALORS QUE LE CORPS NATIF EST TRIVIAL** -- l'entree fait tourner du code la ou le natif
     rend `yield Fix64.FromInt(0)`. C'est du sur-port : il peut diverger, jamais converger.
     Ne s'applique qu'aux playbooks a corps PROPRE ; les concrets a corps HERITE
     (`AdjacentUnitPreferenceTriggeredAbilityPlaybook<T>`) n'ont pas d'itérateur a eux et sont donc
     hors de portee de ce controle, ce que le test dit explicitement.

L'inventaire est re-derive a chaque execution par `probe_419_triggered_playbook_inventory` : le
cliquet ne fige aucun compte (ils changent a chaque build), il fige une PROPRIETE.

ASCII only, 100 % OFFLINE.
"""
from __future__ import annotations

import probe_419_triggered_playbook_inventory as INV


def _rows():
    return INV.build_inventory()


def test_aucun_playbook_porte_nest_non_cable():
    """(1) Toute entree de registre a AU MOINS un porteur reel -- offline ou via le canal live."""
    rows = _rows()
    faults = []
    for face, pk in (("ATTACK", "ported_attack"), ("MOVE", "ported_move"),
                     ("NON-OWNER", "ported_non_owner")):
        for r in rows:
            if r[pk] and not r["wired_live"]:
                faults.append(f"{face}: {r['playbook']} (id={r['ability_id']}) est au registre mais "
                              f"AUCUN porteur ne l'apporte -- ni kit gameconfig/trait, ni relique/"
                              f"mythique/item. Le dispatcher ne l'itere jamais : code INERTE.")
    assert not faults, ("playbooks PORTES mais NON CABLES (le patron #419) :\n  "
                        + "\n  ".join(faults))


def test_aucune_entree_de_registre_ne_porte_un_corps_trivial():
    """(2) Toute entree de registre a corps PROPRE vise un corps natif NON trivial.

    Un corps `yield Fix64.FromInt(0)` (taille calibree sur la base, cf. `_TRIVIAL_MAX`) ne peut rien
    departager : l'enregistrer ajoute du code qui ne peut que s'ecarter du natif."""
    rows = _rows()
    faults = []
    for face, pk, tk, sk in (("ATTACK", "ported_attack", "attack_trivial", "native_attack_sm"),
                             ("MOVE", "ported_move", "move_trivial", "native_move_sm")):
        for r in rows:
            if r[pk] and r[sk] and r[tk]:
                faults.append(f"{face}: {r['playbook']} (id={r['ability_id']}) est au registre alors "
                              f"que son corps natif fait {r[tk.replace('trivial', 'size')]} octets "
                              f"(<= 0x{INV._TRIVIAL_MAX:x} = `yield Fix64(0)`).")
    assert not faults, ("entrees de registre sur un corps natif TRIVIAL :\n  " + "\n  ".join(faults))


def test_les_registres_ne_sont_pas_vides():
    """Garde-fou du cliquet lui-meme : si les registres tombent a zero, les deux tests ci-dessus
    passeraient VIDES et ne garderaient plus rien (un vert qui ment)."""
    atk, mov, nno = INV._registries()
    assert atk and mov and nno, (
        f"registres vides ou introuvables : attack={len(atk)} move={len(mov)} non_owner={len(nno)} "
        f"-- le cliquet ne garde plus rien")
    rows = _rows()
    ported = [r for r in rows if r["ported_attack"] or r["ported_move"] or r["ported_non_owner"]]
    assert ported, ("aucune entree de registre ne s'apparie a une classe native : le croisement "
                    "nom -> `TriggeredAbilityType` est casse, le cliquet est aveugle")
