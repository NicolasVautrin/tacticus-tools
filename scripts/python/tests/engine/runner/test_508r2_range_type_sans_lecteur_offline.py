"""#508-r2 -- les variantes `rangeType` du compteur d'attaques emises (`@+0x28` Ranged /
`@+0x2c` Melee) sont ECRITES par le natif a chaque attaque et LUES par PERSONNE. Ce fichier garde
ce verdict au lieu de le laisser se perimer en prose.

CE QUE LE DECOMPILE DIT, relu sur le build COURANT `t6dpr4k06g` :

    IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade(this, target,
                                                                               rangeType, crits):
        this.<+0x50> = target.Id;
        if (this.<+0x40> != null) {                       // HashSet unitsAttackedThisTurn
            if (Count(this.<+0x40>) == 0) this.<+0x30> += 1;
            Add(this.<+0x40>, target.Id);
            this.<+0x20> += 1;                            // TotalAttacksMade      (porte, #926)
            this.<+0x54> += crits;                        // CriticalHits          (porte, #521-r10)
            this.<+0x24> += 1;                            // AttacksMadeThisTurn   (porte, #508-r1)
            if (rangeType.HasValue && rangeType.Value == 1) this.<+0x2c> += 1;   // Melee   NON PORTE
            if (rangeType.HasValue && rangeType.Value == 2) this.<+0x28> += 1;   // Ranged  NON PORTE
        }

    IdunBattle.Entities.Formulas.AmountOfAttacksMadeThisTurnFormula$$Calculate(this, entities, _):
        foreach (e in this.<+0x10>.Select(entities)) {
            st = e.GetComponent<ActorStatisticsComponent>();
            nullable = this.<+0x18>;                      // Nullable<AttackRangeType> DE LA FORMULE
            if      (nullable.HasValue && nullable.Value == 1) total += st.<+0x2c>;   // Melee
            else if (nullable.HasValue && nullable.Value == 2) total += st.<+0x28>;   // Ranged
            else                                              total += st.<+0x24>;   // TOTAL
        }

LE RECENSEMENT, EXHAUSTIF PAR CONSTRUCTION (xrefs, pas echantillon) :

  * `AmountOfAttacksMadeThisTurnFormula$$.ctor` a **UN SEUL** appelant :
    `IdunBattleLogic.Entities.DSLFormulas$$TimesAttackMadeThisTurn`. C'est donc la SEULE porte par
    laquelle `@+0x18` peut recevoir une valeur.
  * `DSLFormulas$$TimesAttackMadeThisTurn` a **QUATRE** call-sites pour **TROIS** abilities, et les
    quatre passent litteralement `(void *)0x0` en 3e argument -- LU un par un le 2026-08-18 :
      - `...Triggered.Loki.IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger`  (x1)
      - `...Triggered.Loki.LegacyOfCombatAbility$$CreateTrigger`                 (x1)
      - `...Active.Loki.LeadingTheChargeAbility$$ExecuteBehaviour`               (x2)
  * `ActorStatisticsComponent` n'expose AUCUN getter sur `@+0x28` / `@+0x2c` : hors de la formule
    ci-dessus, rien ne peut les lire.

=> les deux compteurs sont du code natif ECRIT-MAIS-JAMAIS-LU. Les porter cote Python serait un
canal SANS LECTEUR (patron #419), donc non validable : son premier test devrait FABRIQUER une
demande que le jeu ne produit pas. Doctrine « pas de porteur = speculatif ». **PORT REFUSE.**

CE QUI FERAIT ROUGIR CE FICHIER -- et c'est tout son objet :
  * un appel porte de `unit_attacks_made_this_turn` qui demanderait une portee (etage 2) ;
  * l'apparition d'un compteur par portee sur `UnitComponent` sans lecteur, ou l'inverse (etage 3) ;
  * le DEMENAGEMENT de `register_attack_made` vers un `FinishAttackOperation` porte (etage 4) --
    c'est la condition de PORTABILITE qui manque aujourd'hui, pas le decompile.

ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from engine.runner.components import (UnitComponent, register_attack_made,
                                      unit_attacks_made_this_turn)
from engine.runner.state import State

#: Ce fichier ne peut pas changer de verdict sans qu'un de ces chemins bouge. `engine/**` en entier
#: parce que les etages 2 et 4 y BALAIENT tous les sites d'appel -- un module qui commence a lire le
#: compteur, ou qui deplace son ecrivain, change le verdict. Le build est declencheur : un
#: renumerotage des `AttackRangeType` changerait le sens des deux offsets.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/**/*.py",),
    "build": True,
    "toujours": False,
    "raison": "Il garde le verdict '`@+0x28`/`@+0x2c` sont ECRITS par le natif et LUS par "
              "personne, donc leur port serait un canal sans lecteur'. Les quatre call-sites "
              "natifs de `IdunBattleLogic.Entities.DSLFormulas$$TimesAttackMadeThisTurn` passent "
              "un `Nullable` VIDE ; le port a les quatre memes, tous a deux arguments. Un "
              "changement de build peut renumeroter `AttackRangeType`, d'ou `build: True`.",
}

ENGINE = pathlib.Path(__file__).resolve().parents[3] / "engine"

#: Les TROIS modules du port qui portent les TROIS abilities natives. Sert de TEMOIN de non
#: degenerescence -- pas de liste blanche : l'etage 2 balaie `engine/**` en entier et n'utilise
#: cette table que pour refuser de conclure sur un gisement vide.
MODULES_ATTENDUS = {
    "engine/runner/abilities/loki/leading_the_charge.py",              # LeadingTheCharge (x2)
    "engine/runner/operations/triggers/loki/icon_of_obstinacy.py",     # IconOfObstinacy
    "engine/runner/operations/triggers/loki/legacy_of_combat.py",      # LegacyOfCombat
}

#: Ce que le natif designe par les deux offsets. Ecrit par le NOM, jamais par l'ordinal nu.
MELEE, RANGED = 1, 2               # `AttackRangeType.Melee` / `.Ranged`, LUS aux octets de
#                                    `ActorStatisticsComponent$$RegisterAttackMade`


def _appels(nom: str) -> list:
    """Tous les sites d'appel de `nom` dans `engine/**`, DERIVES de l'AST. Rend
    `(chemin, ligne, nb_args_positionnels, kwargs)`."""
    out = []
    for p in sorted(ENGINE.rglob("*.py")):
        arbre = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            appele = (n.func.id if isinstance(n.func, ast.Name)
                      else n.func.attr if isinstance(n.func, ast.Attribute) else None)
            if appele == nom:
                out.append((p.relative_to(ENGINE.parent).as_posix(), n.lineno, len(n.args),
                            tuple(sorted(k.arg for k in n.keywords))))
    return out


# ------------------------------------------------------------ 1. LE TEMOIN de non-degenerescence
def test_1_le_gisement_existe_et_le_compteur_TOTAL_est_bien_porte():
    """Les trois assertions des etages suivants sont des comptes ATTENDUS BAS. Sur un gisement
    VIDE -- fonction renommee, modules disparus -- elles passeraient au vert en n'ayant RIEN
    regarde. On exige donc d'abord que le gisement soit la, et que le bras `rangeType = null` du
    natif (`@+0x24`) soit reellement porte et EXECUTABLE."""
    appels = _appels("unit_attacks_made_this_turn")
    assert appels, "aucun appelant de `unit_attacks_made_this_turn` : gisement vide"
    modules = {a[0] for a in appels}
    manquants = sorted(MODULES_ATTENDUS - modules)
    assert not manquants, (
        "les modules %r ne lisent plus le compteur -- les trois consommateurs natifs de "
        "`DSLFormulas$$TimesAttackMadeThisTurn` ne sont plus tous portes, et le recensement "
        "ci-dessous ne couvre plus ce que la fiche #508-r2 decrit." % (manquants,))
    # Le bras `null` EXECUTE : deux attaques, deux cibles, le compteur TOTAL avance de 2.
    st = State()
    st.add_entity(1).add_component(UnitComponent(visual_id="a", alive=True))
    st.add_entity(2).add_component(UnitComponent(visual_id="b", alive=True))
    st.add_entity(3).add_component(UnitComponent(visual_id="c", alive=True))
    assert unit_attacks_made_this_turn(st, 1) == 0
    register_attack_made(st, 1, 2, total_crits=0)
    register_attack_made(st, 1, 3, total_crits=0)
    assert unit_attacks_made_this_turn(st, 1) == 2, (
        "`@+0x24` n'avance pas : le bras `rangeType = null` n'est pas porte, et le verdict "
        "'seul le total est lu' n'a plus de sujet.")


# ----------------------------------------------- 2. AUCUN LECTEUR PORTE NE DEMANDE UNE PORTEE
def test_2_les_quatre_call_sites_portes_passent_tous_rangeType_null():
    """LE CLIQUET PRINCIPAL. Le port materialise `TimesAttackMadeThisTurn(x, rangeType)` par
    `unit_attacks_made_this_turn(state, unit_id)` -- une signature qui n'a PAS de portee, parce que
    les quatre call-sites natifs passent tous `(void *)0x0`. Un appel a trois arguments (ou avec un
    mot-cle) signifierait qu'un consommateur reclame une variante : la branche `@+0x28`/`@+0x2c`
    deviendrait EXIGIBLE, avec le vecteur de confrontation qui manque aujourd'hui.

    Le balayage est DERIVE de l'AST de tout `engine/**` -- une liste de fichiers ne pourrait pas
    montrer l'appel qu'elle a oublie."""
    fautifs = [a for a in _appels("unit_attacks_made_this_turn") if a[2] != 2 or a[3]]
    assert not fautifs, (
        "REACHABILITE OUVERTE : %d appel(s) de `unit_attacks_made_this_turn` reclament autre chose "
        "que le bras `rangeType = null` : %r. Les variantes Melee (`@+0x2c`) et Ranged (`@+0x28`) "
        "d'`ActorStatisticsComponent` deviennent EXIGIBLES -- porter #508-r2 AVEC ce consommateur "
        "comme vecteur, et threader la nature de l'attaque jusqu'a `register_attack_made`."
        % (len(fautifs), fautifs))


# ------------------------------------- 3. L'EQUIVALENCE : ni champ sans lecteur, ni lecteur sans champ
def test_3_aucun_compteur_par_PORTEE_sur_le_composant_ni_de_lecteur_pour_lui():
    """L'invariant est l'EQUIVALENCE, pas l'absence. Aujourd'hui les deux valent FAUX. Poser le
    champ sans lecteur serait le patron #419 (un canal que rien n'exerce) ; poser un lecteur sans
    champ serait une lecture qui ment. Les deux doivent bouger ENSEMBLE, dans le meme commit.

    ⚠ Le discriminant est le NOM DE PORTEE, pas le mot << attack >> : `UnitComponent` porte
    legitimement six compteurs d'attaque (le total du tour, le cumul de bataille, les recus...),
    et un critere trop large les accuserait tous."""
    portee = tuple(s for s in getattr(UnitComponent, "__slots__", ())
                   if any(m in s.lower() for m in ("melee", "ranged")) and "attack" in s.lower())
    lecteurs = tuple(a for a in _appels("unit_attacks_made_this_turn") if a[2] != 2 or a[3])
    assert bool(portee) == bool(lecteurs), (
        "DESEQUILIBRE #508-r2 : champs par portee sur `UnitComponent` = %r, lecteurs qui en "
        "demandent une = %r. Un canal pose sans lecteur n'est pas validable ; un lecteur sans "
        "canal lit du vide." % (portee, lecteurs))
    assert portee == (), (
        "les compteurs par portee sont apparus (%r) -- si c'est deliberement, #508-r2 est porte et "
        "cette garde doit etre REECRITE en confrontation, pas retiree." % (portee,))


# --------------------------------- 4. LA CONDITION DE PORTABILITE : le RANG de `register_attack_made`
def test_4_le_rang_de_l_ecrivain_n_a_pas_change():
    """CE QUI MANQUE POUR PORTER, rendu executable. Le natif appelle `RegisterAttack` (slot
    `IOperationProcessor` 0x4a) depuis `IdunBattle.Operations.FinishAttackOperation$$Execute`, UNE
    FOIS PAR CIBLE a la cloture, avec un `Nullable<AttackRangeType>` TOUJOURS renseigne (il vient du
    slot 4 d'`IBattleQuery`, `BattleQuery$$GetAttackRangeType`, dont le port a l'etage depuis
    #951-r1). Le port, lui, appelle `register_attack_made` depuis le PIPELINE DE DEGAT : deux rangs
    differents, et c'est ce qu'il faudra reconcilier le jour ou un lecteur apparaitra -- pas
    seulement threader un argument.

    Ce test fige donc l'etat de ce prealable. Il rougit si l'ecrivain demenage ou se multiplie,
    c'est-a-dire exactement quand la reponse a << peut-on porter ? >> change."""
    sites = _appels("register_attack_made")
    assert len(sites) == 1, (
        "`register_attack_made` a desormais %d sites d'appel (%r) : le rang de l'ecrivain a change, "
        "et le prealable ecrit dans #508-r2 (<< reconcilier `FinishAttackOperation` et le pipeline "
        "de degat >>) doit etre re-tranche." % (len(sites), sites))
    chemin, _ligne, n_args, kwargs = sites[0]
    assert chemin == "engine/runner/operations/damage.py", (
        "l'ecrivain a demenage vers %r. S'il s'agit d'un `FinishAttackOperation` porte, le rang "
        "natif est atteint et #508-r2 devient PORTABLE : threader le `rangeType` depuis le slot 4 "
        "d'`IBattleQuery` (`services/battle_query.get_attack_range_type`, deja pose par #951-r1)."
        % (chemin,))
    assert (n_args, kwargs) == (3, ("total_crits",)), (
        "la signature du site d'ecriture a change (%r, %r) -- si un `range_type` y est apparu, "
        "#508-r2 est en cours de portage et cette garde doit suivre." % (n_args, kwargs))


# --------------------------------------------------- 5. LES DEUX ORDINAUX, ECRITS PAR LEUR NOM
def test_5_les_deux_offsets_ne_sont_pas_interchangeables():
    """Garde de LECTURE, pas de comportement. `RegisterAttackMade` incremente `@+0x2c` sur
    `Melee(1)` et `@+0x28` sur `Ranged(2)` -- LU aux octets, dans cet ordre, qui n'est PAS celui
    qu'on devinerait des offsets croissants. `AmountOfAttacksMadeThisTurnFormula$$Calculate` les
    relit dans le MEME appariement. Toute future tranche qui inverserait les deux ecrirait un
    compteur juste sous le mauvais nom, en silence."""
    assert (MELEE, RANGED) == (1, 2)
    appariement = {MELEE: "@+0x2c", RANGED: "@+0x28"}
    assert appariement[MELEE] == "@+0x2c" and appariement[RANGED] == "@+0x28"


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
