"""`IdunBattle.Core.LeftOverDamage` + les TROIS call-sites de
`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` -- le CANAL par lequel un coup
gaspille du degat sur une cible morte, et par lequel `HazeOfCorruption` reporte ce degat sur un
relais (case-209).

================================================================================================
RE (decompile ghidra, build `gqfc5mff6c`) -- case-209
================================================================================================

`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit(this, target, damage, hitInfo, flag)`
recupere le composant de la CIBLE dont le champ `+0x90` est la `List<LeftOverDamage>` et y ajoute
`LeftOverDamage(damage /* struct Damage, 16 octets */, hitInfo[5..], flag)`. La struct `Damage`
occupe `LeftOverDamage+0x6c` :

    IdunBattle.Core.Damage$$.ctor(this, p2, p3) : `+0x00 = p2`, `+0x04 = p3`, `+0x08 = +0x0c = 0`
    IdunBattle.Core.Damage$$GetTotal          : `+0x04 + +0x08 + +0x0c`

d'ou, cote consommateur, `LeftOverDamage+0x6c` = le TYPE et `LeftOverDamage+0x70` = le MONTANT
(c'est exactement ce que relit
`IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour`).

Les TROIS call-sites de `…$$Execute`, avec le montant qu'ils poussent (`param_5` = le message de
degat : `+0x00` DamageType, `+0x04/+0x08/+0x0c` les montants sante/armure/bouclier, `+0x98` la
BASE nominale du coup) :

  (A) `UnitExtensions.HasFlag(target, 8 = Overkilled)` -> `Damage(type, param_5[0x98])`, flag
      LITTERAL 1, puis `return` : AUCUN degat applique, AUCUN evenement emis.
  (B) `HealthComponent.IsDead(health)` evalue AVANT l'application -> `Damage(type, param_5[0x98])`,
      flag = ce meme `IsDead`. Pas de `return`.
  (C) apres l'application, sous `0 < applique` et `IsDead` evalue APRES ->
      `Damage(type, demande_sante - applique_sante)`, flag = l'`IsDead` d'AVANT.

=> DEUX regimes, et un seul depend du tirage :
     * le coup qui TUE (la cible etait vivante, `applique > 0`)  -> **reste d'overkill** (C) ;
     * un coup sur une cible DEJA morte (`applique == 0`)        -> **la BASE nominale** (A)/(B),
       c'est-a-dire un montant INDEPENDANT du jet de degat de ce coup.

MESURE LIVE qui TRANCHE (`probe_209_haze_damage_transfer.py`, board MC1_67, `deathBlightlord` vs
`astraBullgryn` + un relais sur un voisin commun) -- l'arme est a 3 coups, cellule reduite
`(2087, 3131)` :

| seed | PV cible | coups d'arme      | transferts observes sur le relais |
|------|----------|-------------------|-----------------------------------|
| 777  | 8000     | 2711, 2447, 2196  | aucun (la cible survit)           |
| 777  | 6000     | 2711, 2447, 842   | **1354** = 2196 - 842   (site C)  |
| 777  | 5000     | 2711, 2289, 0, 0  | **158** = 2447 - 2289   (site C), puis **2609**, puis **1397** |
| 88   | 5000     | 2323, 2677, 0, 0  | **245** = 2922 - 2677   (site C), puis **2609**, puis **1397** |

Les deux seeds ont des jets d'arme DIFFERENTS et rendent le MEME **2609** au 2e transfert :
`2609 = (2087 + 3131) / 2` = le milieu EXACT de la cellule = la base nominale. C'est ce qui
REFUTE « le leftover est le jet du coup » et etablit le champ `+0x98`. Le 3e transfert (**1397**,
profil Toxic) est le meme invariant pour le coup BONUS de `HazeCorruption_BonusHitAbility`.

================================================================================================
LE PORT
================================================================================================
Le natif appelle `ApplyDamageOperation` UNE FOIS PAR COUP ; le port applique le degat en UN bloc
au chokepoint `AttackDamageOperation._apply_damage_pipeline` et RE-JOUE la sequence des coups pour
les decisions qui en dependent -- exactement ce que fait deja `_did_overkill` juste au-dessus
(meme patron, meme source `hits_result`). `record_left_over_damages` est ce re-jeu.

RESIDU NOMME : le flag (`LeftOverDamage+0x7c`) n'est pas porte. Son seul consommateur connu est
`ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` (DakkaDakkaDakka), qui a son propre port
DERIVE (`abilities/behaviours/combat.py::_left_over_hits`) et ne lit pas cette liste-ci.
"""
from __future__ import annotations

from typing import Optional

from ..state import Component, State
from ..components import UnitFlagsComponent


class LeftOverDamagesComponent(Component):
    """Mirror du champ `+0x90` (`List<LeftOverDamage>`) du composant de degat de l'entite : la
    liste des degats GASPILLES sur cette unite, dans l'ordre d'ajout.

    `entries` = liste de dicts `{"amount": int, "profile": str|None}` -- `amount` = `Damage+0x04`
    (`LeftOverDamage+0x70`), `profile` = le pendant porte de `Damage+0x00` (`LeftOverDamage+0x6c`,
    `DamageType`) : le port manipule le PROFIL par son nom gameconfig partout ailleurs (c'est lui
    qui porte le percage), pas l'id numerique."""
    __slots__ = ("entries",)

    def __init__(self, entries: Optional[list] = None):
        self.entries = list(entries or [])


def left_over_damages(state: State, unit_id: int) -> list:
    """`HazeOfCorruption_DamageTransferEffect$$GetLeftOverDamagesFromEntity(entity)` =
    `entity.<composant>.LeftOverDamages` (champ `+0x90`). Liste VIDE si l'unite n'en a aucune."""
    e = state.get_entity(unit_id) if unit_id is not None else None
    c = e.get_component(LeftOverDamagesComponent) if e is not None else None
    return list(c.entries) if c is not None else []


def _append(state: State, unit_id: int, amount: int, profile) -> None:
    e = state.get_entity(unit_id)
    if e is None or int(amount) <= 0:
        return
    c = e.get_component(LeftOverDamagesComponent)
    if c is None:
        c = e.add_component(LeftOverDamagesComponent())
    c.entries.append({"amount": int(amount), "profile": profile})


def record_left_over_damages(state: State, target_id: int, tgt, hp_before,
                             total: int, profile, hits_result: Optional[dict],
                             base_nominal: Optional[int]) -> None:
    """Re-joue la sequence des coups du groupe et pousse une entree par coup GASPILLE, mirror des
    trois call-sites d'`ApplyDamageOperation$$AddLeftoverHit` (cf. l'en-tete du module).

    `base_nominal` = `param_5[0x98]` : la BASE du coup (milieu de la cellule reduite), ce que les
    sites (A)/(B) poussent. `None` -> les coups sur cadavre ne poussent rien (degradation
    CONSERVATRICE et documentee : mieux vaut un transfert manquant qu'un montant invente).

    `hp_before` = PV au debut du GROUPE ; le natif, lui, relit les PV a chaque coup -- le re-jeu
    cumulatif ci-dessous donne la meme suite tant qu'aucune source exterieure ne soigne entre deux
    coups d'une meme serie (aucun cas connu)."""
    if tgt is None or hp_before is None:
        return
    seq = [int(x) for x in ((hits_result or {}).get("per_hit_health") or [])] or [int(total or 0)]
    # `UnitFlag.Overkilled` DEJA pose a l'entree du groupe -> site (A) pour TOUS les coups.
    fl = tgt.get_component(UnitFlagsComponent)
    already_overkilled = bool(fl is not None and fl.has(UnitFlagsComponent.OVERKILLED))
    hp = int(hp_before)
    for health_dmg in seq:
        if already_overkilled or hp <= 0:
            # (A)/(B) : la cible etait deja morte a l'entree de CE coup -> la BASE nominale entiere.
            _append(state, target_id, base_nominal or 0, profile)
            continue
        applied = min(hp, int(health_dmg))
        hp -= applied
        if hp <= 0 and applied > 0:
            # (C) : le coup TUE -> `demande_sante - applique_sante`.
            _append(state, target_id, int(health_dmg) - applied, profile)
