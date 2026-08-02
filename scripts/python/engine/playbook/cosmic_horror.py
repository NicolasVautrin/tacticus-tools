"""`IdunBattle.AI.Playbook.Loki.CosmicHorrorPlaybook` -- face ATTACK du triggered `CosmicHorror`
(1277), passif de `genesPatriarch` << The Patermine >> (HERO, kind `lineup`) et de 3 npc
(`genesBossPatriarch`, `genesBossPatriarchLHE`, `genesNpcPatriarch`) : 4 porteurs, tranche 6 des
residus ATTACK de #419.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle et Boltstorm (`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.CosmicHorrorPlaybook$$CalculateAttackUtilityInStepsInternal` monte la
SM `d__3` -- et sa disposition se LIT dans ce wrapper, jamais par analogie : il ecrit
`sm@+0x20 = case`, `sm@+0x28 = this` (le PLAYBOOK) et `sm@+0x30 = getUtilityVal` (le delegue
scorer), `sm@+0x10 = 0` (state). C'est la meme disposition a TROIS champs que
`SaviorProtocolsPlaybook.d__5`, et PAS celle de `BarbedOvipositor` (deux champs) ni celle de la face
MOVE de cette meme classe (`d__2`, qui n'ecrit AUCUN des trois -- cf. plus bas). Corps
`CosmicHorrorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`, UN SEUL
`yield` :

    int v = 0;
    Tile tile = case.CasterPosition.MainTile;                 // UtilityAttackCase@+0x18
    IEntity u = UnitExtensions.GetUnit(tile, this.<>4__this.State);
    if (u != null && UnitExtensions.HasTrait(u, 0x41d /* UnitTrait.Decoy */)
                  && UnitExtensions.IsFriend(u, case.Caster /* @+0x10 */, state))
        v = getUtilityVal("COSMICHORROR_StepOnDecoyToAttack");
    yield return Fix64.op_Implicit(v);

Cinq lectures qui ne se devinent pas :

1. **La tuile lue est celle du CASTER, pas celle de la cible.** Le symbole que Ghidra donne au
   getter est `IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile` -- un corps
   `UnitPosition.get_MainTile(this + 0x18)` DEDUPLIQUE par l'ICF : sur un `UtilityAttackCase`,
   `+0x18` est `CasterPosition` (lu au `.ctor` et aux trois usines `Base` / `ForDamagePrediction`),
   donc c'est `case.CasterTile`. Le nom du symbole designe la classe PROPRIETAIRE du corps, pas le
   type reellement passe -- s'y fier ici ferait lire la tuile du mouvement d'un case d'attaque.

2. **`GetUnit(tile, state)` est l'OCCUPANT de la tuile**, pas le caster. La surcharge appelee est
   celle qui accepte n'importe quelle entite (`IdunBattle.Entities.UnitExtensions$$GetUnit`, celle
   dont le xref entrant depuis `d__3$$MoveNext` est UNCONDITIONNEL) : elle rend l'entite telle
   quelle si c'est une unite, resout `TileContentComponent.IsFilled` -> l'entite contenue si c'est
   une tuile, et remonte au parent si c'est un pied. Une tuile n'a qu'UN occupant.

3. **Le terme n'est donc PAS un terme de cible : c'est un terme de TUILE D'ATTAQUE.** Il ne vaut
   que dans le regime ou le caster attaque DEPUIS une tuile deja occupee -- possible parce que
   `IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable` laisse le movable set contenir les
   tuiles occupees par une unite `Steppable`. Le nom de la cle le dit : `StepOnDecoyToAttack`.
   Consequence directe : le terme est CONSTANT en la cible, et il ne bouge qu'en DEPLACANT le
   caster -- c'est le seul playbook attack porte a ce jour dont la sortie ne depend d'AUCUNE
   propriete de la cible.

4. **`0x41d` = 1053 = `UnitTrait.Decoy`** -- enum a QUALIFIER : a id egal, `TriggeredAbilityType`
   1053 = `BroodProgenitor`, `ActiveAbilityType` 1053 = `DevoutPush`, `EffectType` 1053 =
   `ShadowInTheWarp_LessDmg_Effect`. C'est le MEME trait, au meme id, que la branche Decoy de
   `SteppableUnitUtility` (feuille MOVE 20) et que le `FilterAdjacentFriends` de
   `SpiritualLeaderPlaybook`. ⚠ Le natif ne filtre PAS sur `Steppable` ici (contrairement a
   `TileExtensions$$GetSteppableUnit` de la feuille 20) : il prend l'occupant tel quel et ne teste
   que `Decoy`. Les deux traits coincident sur les deux seuls porteurs du catalogue
   (`genesDecoy` npc et `genesSmnDecoy` summon portent `['Steppable', 'Decoy']`), mais c'est une
   COINCIDENCE de donnees, pas le gate -- mirrorer `Steppable` ici serait un ajout.

5. **La sortie est un poids BC, pas un litteral** : le slot de string literal du corps est
   `COSMICHORROR_StepOnDecoyToAttack` -- LU (`probe_212_bc_key_literals.py` sur ce symbole), pas
   devine. `Utilities.Default.TriggeredAbilities` : **10** au seed BC servi ET **10** au gameconfig
   VIVANT (les deux concordent -> pas de piege #271). Le playbook n'a pas de `.cctor` : le literal
   est dans le corps, meme forme que `SaviorProtocols` et `BarbedOvipositor`, l'inverse de
   `Lakrimae`.

Le gate d'ami (`IsFriend(occupant, case.Caster, state)`) rejoue l'asymetrie deja notee sur la
feuille 20 : la feuille MOVE PENALISE de -50 (`SteppableUnit.FriendlyDecoy`) le fait de marcher sur
son propre leurre, tandis que ce playbook-ci en REND 10 quand la tuile sert a attaquer. Les deux
termes ne s'annulent pas (ils vivent dans deux composites differents -- Tile(7) contre Damage(34))
mais ils vont bien en sens INVERSE : le Patriarch n'ecrase son leurre que s'il y gagne une attaque.

## Face MOVE : `yield Fix64(0)` CONSTANT -- decompile LU, ce n'est pas un trou

`CosmicHorrorPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` est un unique
`yield return Fix64.op_Implicit(0)`, et son wrapper `$$CalculateMovementUtilityInStepsInternal`
n'ecrit meme pas le case dans la SM (state seul). `probe_212_bc_key_literals.py` confirme :
AUCUN string literal lu. Elle n'entre donc pas au registre `TRIGGERED_MOVE_PLAYBOOKS`, et cette
absence EST le comportement natif -- meme forme que `Lakrimae`, `BarbedOvipositor` et
`Neuroparasite`, a l'inverse de `SaviorProtocols` (residu `#443-r1`).

## Substrat cote port -- ce que ce terme exige, et qui l'ecrit

Le corps ne lit ni stats, ni effets, ni prediction : uniquement la POSITION d'attaque et
l'occupant de cette tuile. Les deux canaux existent deja dans la `Scene` (`pos_by_id` +
`units[].alive` pour l'occupant, `_entity_traits` pour le trait) et `attack_tile` est deja le 5e
parametre du dispatcher -- aucune piece neuve n'est requise, donc pas de patron
« porte + INERTE ». `prediction` (`UtilityAttackCase@+0x28`, canal #438) est ACCEPTE et IGNORE,
comme le corps natif qui ne lit pas ce champ.
"""
from __future__ import annotations

from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType
from .prediction._shared import _entity_traits

# `HasTrait(u, 0x41d)` -- 1053, `UnitTrait.Decoy` (cf. en-tete, point 4 : enum QUALIFIE).
_DECOY = UnitTrait.Decoy.name
# L'UNIQUE string literal de la face ATTACK, lu dans `Utilities.Default.TriggeredAbilities`.
_WEIGHT_KEY = "COSMICHORROR_StepOnDecoyToAttack"


def tile_occupant(scene, tile) -> "int | None":
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(tile, state)` -- l'unite qui OCCUPE `tile`.

    Le natif resout `TileContentComponent.IsFilled` puis l'entite contenue, et remonte au parent si
    c'est un pied ; une tuile n'a qu'UN occupant (le composant ne porte qu'un id), donc la premiere
    unite VIVANTE dont la `MainTile` est `tile` est LA reponse -- et une unite morte ne remplit plus
    sa tuile (`RemoveUnitOperation` vide le `TileContentComponent`), d'ou le filtre `alive`.

    `scene.pos_by_id` porte la MainTile de chaque unite ; les pieds d'une unite multi-tuiles n'y
    figurent pas separement, ce qui rend la remontee au parent implicite. `None` = tuile inconnue ou
    libre -- meme sortie que le natif quand `IsFilled` est faux."""
    if tile is None:
        return None
    alive = {u.get("id") for u in (scene.units or ()) if u.get("alive")}
    for uid, pos in (scene.pos_by_id or {}).items():
        if pos == tile and uid in alive:
            return uid
    return None


class CosmicHorrorPlaybook:
    """`CosmicHorrorPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1277 -- l'id passe par
    `$$.ctor` a la base `TriggeredAbilityPlaybook<T>` est bien `0x4fd`). Seule la face ATTACK a un
    corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.CosmicHorror)      # 1277 = 0x4fd

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` (cf. en-tete) : le
        poids `COSMICHORROR_StepOnDecoyToAttack` quand la TUILE D'ATTAQUE est occupee par un leurre
        AMI, 0 sinon. Aucun terme de cible : `case_tgt_id` et `prediction` ne sont pas lus, comme le
        corps natif qui ne touche que `case@+0x18` (la position du caster) et `case@+0x10` (le
        caster)."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        occ = tile_occupant(sc, attack_tile)                      # GetUnit(case.CasterTile, state)
        if occ is None:
            return 0.0
        if _DECOY not in _entity_traits(sc, occ):                 # HasTrait(u, 0x41d)
            return 0.0
        # `IsFriend(u, case.Caster, state)` = meme `GetCurrentPlayer(...).id` des deux cotes ; cote
        # port c'est `scene.team`, le MEME substrat que tous les `IsFriend`/`IsEnemy` deja portes.
        t_occ, t_att = sc.team(occ), sc.team(attacker_uid)
        if t_occ is None or t_att is None or t_occ != t_att:
            return 0.0
        return float(ctx.wt.triggered(_WEIGHT_KEY))               # GetUtilityValue(<cle>)
