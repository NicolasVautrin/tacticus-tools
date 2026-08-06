"""Les TROIS batchs de `IdunBattle.AI.Playbook.Loki.PlagueWindPlaybook$$MakeDamagePredictions`
(ability `1035 PlagueWind`) et de
`IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$MakeDamagePredictions`
(ability `1093 MortarionsPlagueWind`). `#27-r5-r1`.

LES DEUX PLAYBOOKS, remis en C# depuis le decompile -- MEME squelette, DEUX differences
--------------------------------------------------------------------------------------

    t1    = StrikeFromTheShadowsAbility$$GetTarget(ability)              // <DSLSelectors+0x60> = Target
    t2    = StormOfWrathAbility$$<ExecuteBehaviour>b__1_0(ability, t1)   // Enemies(Caster, AdjacentUnits(t1,1,3), 3)
    t3    = PlagueWindAbility$$GetTargets3(ability, t1, t2)              // Unique(Enemies(Caster,
                                                                         //   AdjacentUnits(t2,1,3),3)) - t1 - t2
    d1,d2,d3 = <les trois formules de degat, cf. ci-dessous>
    hits  = AActiveAbility$$GetHits(ability)                             // GetNumberConstant(0x2f = nrOfHits)
    prof  = <le profil, cf. ci-dessous>
    list  = new List<ProbableDamageEvent>()
    list.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, target, t1, d1, hits, prof, null, 0) )
    list.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, target, t2, d2, hits, prof, null, 0) )
    list.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, target, t3, d3, hits, prof, null, 0) )
    return list;

**Les trois corps de selecteur sont les MEMES FONCTIONS pour les deux playbooks** -- pas des
homonymes, pas des jumeaux : les deux `MakeDamagePredictions` appellent litteralement les memes
adresses (lecture directe des deux decompiles). C'est pourquoi le port les partage
(`runner/abilities/deathguard.plague_wind_wave_selectors`) et pourquoi le nom de cette fonction ne
cite aucune des deux abilities. La deduplication IL2CPP ne masquait pas une ressemblance : elle
masquait l'IDENTITE du code.

LES DEUX DIFFERENCES entre 1035 et 1093
---------------------------------------
1. **Les formules de degat.**

     1035 : d1 = StranglethornCannonAbility$$GetDamageAmountMain      -> AActiveAbility$$MinMaxDamageAverage
            d2 = StranglethornCannonAbility$$GetDamageAmountAdjacent  -> AActiveAbility$$MinMaxDamage2Average
            d3 = PlagueWindAbility$$GetDamage3                        -> AActiveAbility$$MinMaxDamage3Average
     1093 : dN = MortarionsPlagueWindAbility$$GetDamage{1,2,3}
            = If( DSLTriggers$$HasTrait(<DSLSelectors+0x60> = Target, 2 = Summon),
                  Multiply(MinMaxDamage{,2,3}Average, <DSLFormulas+0x28>),
                  MinMaxDamage{,2,3}Average )

   `AActiveAbility$$MinMaxDamage{,2,3}Average` = `Half(Sum(Direct(GetVariableForLevel(<min>)),
   Direct(GetVariableForLevel(<max>))), 0)` avec `(0xc,0xd) = (minDmg,maxDmg)`,
   `(0x36,0x37) = (minDmg_2,maxDmg_2)`, `(0x38,0x39) = (minDmg_3,maxDmg_3)`.

   **`<DSLFormulas+0x28>` est LU, pas suppose.** `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
   alloue cinq constantes partagees et les ecrit a `+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
   `+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)` -- meme classe allouee et meme
   ctor que `IdunBattleLogic.Entities.DSLFormulas$$Direct(amount)`. Le facteur vaut donc **2**, ce
   que l'i2 (« Summons take double damage ») ne faisait que suggerer. La meme table est deja lue
   ailleurs dans le depot (`entities/triggers.is_mechanical` cite `+0x20 = Direct(1)`).

2. **Le PROFIL.** 1093 passe `Nullable(AActiveAbility$$GetDamageProfile(ability))`
   (`GetValueOrDefault(-1)` par-dessus la config) ; 1035 passe
   `IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$GetDamageProfileType(ability)`
   = `AbilityConfiguration$$GetDamageProfile(config)`, c.-a-d. le `Nullable` BRUT. Les deux
   configs portent `damageProfile = Psychic`, donc les deux chemins rendent Psychic : la
   distinction est INOBSERVABLE ici et aucun `profile_override` n'est pose. Elle ne le deviendrait
   que sur une config SANS `damageProfile` (1093 -> enum -1, 1035 -> `Nullable` vide), regime
   qu'aucune des deux n'a.

LE QUIRK QUI NE SE DEVINE PAS : le `HasTrait` porte sur la CIBLE PRINCIPALE
--------------------------------------------------------------------------
`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` construit **UN SEUL** `AbilityEntities`
AVANT sa boucle, avec `target = param_4` (la cible du message, identique pour les TROIS batchs),
puis :

  * evalue la FORMULE `param_6` **une fois, hors boucle** (`local_res20`), sur cet `AbilityEntities` ;
  * evalue le SELECTEUR `param_5` sur le MEME objet -> la liste des entites a frapper ;
  * boucle sur cette liste, et n'y change QUE le `target` passe a
    `DamagePredictionQuery$$GetAttackPrediction` (slot 0xb) et au `ProbableDamageEvent`.

Le `Target` du `HasTrait` est donc **la cible principale**, jamais l'unite frappee : si la cible
est un `Summon`, **les trois vagues entieres** sont doublees, y compris sur des unites qui ne sont
pas des summons ; si elle ne l'est pas, aucune ne l'est, meme si toute la vague 2 est faite de
summons. C'est le meme mold que le quirk deja porte pour Stikkbomb/PlasmaGrenade (`param_4 =
target` invariant), pris ici du cote FORMULE au lieu du cote CIBLE.

CE QUE LE PORT FAISAIT AVANT
----------------------------
Rien de tout cela : 1035 et 1093 n'avaient ni `get_aoe_targets` ni handler, donc le chemin
generique de `make_damage_predictions` rendait **UN** event -- la cible principale, base
`ab.get_damage()`, hits `get_special_hits`. Mesure heritee de #27-r5 (bras A) : `u_full` port
**1.1220 / 5.6097** contre natif **13.2764 / 13.7118**, et le moteur choisissait donc l'AUTRE
cible que le natif sur les trois bras.

DECOUPAGE DU PORT (mirror de la structure native, pas une commodite)
--------------------------------------------------------------------
Le batch 1 EST le chemin generique de `make_damage_predictions` (son selecteur est `Target`, donc
exactement la cible principale) : il ne lui manque que ses ENTREES -> `main_batch_inputs`, consomme
par `_MAKE_DMG_INPUT_OVERRIDES`. Les batchs 2 et 3 ont chacun leur SELECTEUR et leur BASE : ils ne
sont donc ni l'AoE de l'ability (une seule base) ni la cible -> `wave_events`, consomme par
`_MAKE_DMG_EXTRA_EVENTS`, qui s'ajoute APRES la boucle AoE (vide ici) -- l'ordre du natif.

CE QUI RESTE NON PORTE, ET LE DIRE
----------------------------------
* `TargetsSelector$$SelectUniqueUnits(ctx, 3)` : le masque `3` (vivante ET sans le flag `0x11
  NotTargetable`) n'est pas modelise -- `_within` filtre deja les mortes, le flag `0x11` n'a aucun
  substrat sur la face prediction. Residu COMMUN a tous les sets AoE portes.
* L'ORDRE d'enumeration a l'interieur d'une vague (rang de tuile cote port, ordre du natif cote
  natif) : il ne departage que des events de valeur egale, la somme d'utilite est invariante.
"""
from __future__ import annotations

from ...entities.active_ability_type import ActiveAbilityType
from ...entities.formulas import Half, If, Multiply, Sum
from ...entities.selectors.accessors import Target
from ...entities.traits.unit_trait import UnitTrait, trait_name as _trait_name
from ...entities.triggers import HasTrait
from ...dsl.base import AAmountFormula, Const, DslContext
from ..probable_damage_event import ProbableDamageEvent
from ...runner.abilities.deathguard import plague_wind_wave_selectors
from ._shared import _entity_traits
from .abilities import generate_multi_hit_attack_prediction

PLAGUE_WIND = int(ActiveAbilityType.PlagueWind)                          # 1035 = 0x40b
MORTARIONS_PLAGUE_WIND = int(ActiveAbilityType.MortarionsPlagueWind)     # 1093 = 0x445

# `AActiveAbility$$MinMaxDamage{,2,3}Average` -- les couples `(AbilityVariableType.min,
# .max)` que chacune lit, dans l'ordre des trois batchs :
#   MinMaxDamageAverage  -> 0xc  minDmg   / 0xd  maxDmg
#   MinMaxDamage2Average -> 0x36 minDmg_2 / 0x37 maxDmg_2
#   MinMaxDamage3Average -> 0x38 minDmg_3 / 0x39 maxDmg_3
WAVE_DAMAGE_VARS = (("minDmg", "maxDmg"), ("minDmg_2", "maxDmg_2"), ("minDmg_3", "maxDmg_3"))

# `AActiveAbility$$GetHits` = `GetNumberConstant(0x2f)` -- la MEME pour les trois batchs, et
# LITTERALE : le natif ne passe pas par `GetDefaultAttackHits`, donc pas de stat `ExtraHits`.
HITS_CONST = "nrOfHits"


def min_max_damage_average(mn: int, mx: int) -> AAmountFormula:
    """`IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage{,2,3}Average` --
    `Half(Sum(Direct(mn), Direct(mx)), 0)`, les trois corps etant identiques a la paire de
    variables pres. `Half` -> `DivideAmount$$Calculate` -> `AAmountFormula$$RoundFix64Result(., 0)`
    = `Fix64.Round` demi-vers-le-PAIR, le MEME arrondi que `AActiveAbility.get_damage()` sert aux
    abilities du registre `_PREDICTION_MINMAX_AVERAGE` (dont 1035 et 1093 font partie)."""
    return Half(Sum(Const(int(mn)), Const(int(mx))))


def wave_damage_formula(ability_id: int, mn: int, mx: int) -> AAmountFormula:
    """La formule de degat d'UNE vague. 1035 : l'avg nue. 1093 : l'avg sous le `If(Summon)`.

    `IdunBattleLogic.Entities.Abilities.Active.Loki.MortarionsPlagueWindAbility$$GetDamage{1,2,3}` :

        If( DSLTriggers$$HasTrait(<DSLSelectors+0x60> = Target, 2 = Summon),
            Multiply(MinMaxDamage{,2,3}Average, <DSLFormulas+0x28> = Direct(2)),
            MinMaxDamage{,2,3}Average )

    L'operande du `HasTrait` est le selecteur `Target` -- donc la CIBLE PRINCIPALE du cast, pas
    l'unite frappee par la vague (cf. l'en-tete du module : la formule est evaluee UNE fois, hors
    de la boucle de `GenerateMultiHitAttackPredictions`, sur l'`AbilityEntities` du message).

    Toute autre ability que 1093 recoit l'avg nue : c'est la forme de 1035, et c'est aussi la
    degradation JUSTE pour un appelant qui se tromperait d'id (aucun facteur invente)."""
    avg = min_max_damage_average(mn, mx)
    if int(ability_id) != MORTARIONS_PLAGUE_WIND:
        return avg
    return If(HasTrait(Target(), int(UnitTrait.Summon)),
              Multiply(avg, Const(2)),                      # <DSLFormulas+0x28> = Direct(2)
              avg)


def _has_trait_from_scene(scene):
    """`ctx.has_trait(unit, traitId)` = `UnitExtensions$$HasFlag`, substrat de la face PREDICTION.

    MEME foyer que `make_damage_predictions` (`_entity_traits`, #267-r1) : substrat d'ENTITE, jamais
    une relecture du kit gameconfig par `visualId` -- sans quoi le pseudo-trait d'ALLIANCE et les
    traits poses en bataille manqueraient, et le gate `Summon` serait faux dans les deux sens."""

    def _has_trait(u, trait) -> bool:
        uid = (u or {}).get("id")
        return uid is not None and _trait_name(trait) in _entity_traits(scene, uid)
    return _has_trait


def dsl_context(scene, caster_id: int, target_id) -> DslContext | None:
    """L'`AbilityEntities` unique que `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions`
    construit avant sa boucle, porte sur le substrat `Scene`.

    Champs poses = ceux que le decompile renseigne et que ces arbres LISENT : `caster` (referent
    d'inimitie de `Enemies`, `<DSLSelectors+0x48>`), `target` (`<+0x60>`, l'ancre de la vague 1 ET
    l'operande du `HasTrait`), `board`/`elev_by_pos` (le voisinage hex + la porte d'elevation
    d'`IterateAdjacentTiles`), `has_trait` (le gate `Summon` de 1093).

    ⚠ AUCUN `caster_pos`. Le natif passe bien `casterPosition` a la fonction, mais il ne l'ecrit
    QUE dans les champs de POSITION de l'`AbilityEntities` (`+0x40 get_MainTile(casterPosition)`,
    `+0x48 casterPosition`) -- or aucun noeud de ces trois vagues ne lit une tuile de caster : la
    chaine est ancree sur `Target`. Le SET est donc invariant sur le sweep de tuiles ; poser un
    `caster_pos` ici serait sans effet, mais aussi sans lecture.

    `None` si le caster n'est pas dans la scene (aucun event invente)."""
    units = list(getattr(scene, "units", None) or [])
    by_id = {u.get("id"): u for u in units}
    caster = by_id.get(caster_id)
    if caster is None:
        return None
    return DslContext(units=units, caster=caster, target=by_id.get(target_id),
                      board=getattr(scene, "board", None),
                      elev_by_pos=getattr(scene, "elev_by_pos", None),
                      has_trait=_has_trait_from_scene(scene))


def _wave_base(ability_id: int, ab, cfg, wave: int, dctx: DslContext) -> int:
    """Base d'une vague = `<formule de la vague>` evaluee sur l'`AbilityEntities` du message.

    Les deux variables sont lues au niveau PER-ABILITY et scalees par le multiplicateur de rarete,
    exactement comme `AActiveAbility.get_damage()` le fait pour la vague 1 -- c'est le
    `GetVariableForLevel(config, <var>, abilityState, 0)` du decompile."""
    mn_key, mx_key = WAVE_DAMAGE_VARS[wave]
    lvl, mult = ab.level, ab.multiplier
    mn = cfg.get_variable_for_level(mn_key, lvl, 0, mult)
    mx = cfg.get_variable_for_level(mx_key, lvl, 0, mult)
    if not (mn or mx):
        return 0
    return int(wave_damage_formula(ability_id, mn, mx).evaluate(dctx))


def main_batch_inputs(scene, caster_id: int, target_id, ab, cfg) -> dict:
    """Entrees du batch 1 (`param_5 = <Target>`), que le chemin generique de
    `make_damage_predictions` couvre deja en STRUCTURE mais pas en VALEURS.

      * `hits` = `AActiveAbility$$GetHits` = `GetNumberConstant(0x2f = nrOfHits)` **LITTERAL**. Le
        chemin generique passe par `ab.get_special_hits` = `GetDefaultAttackHits(nrOfHits,
        ExtraHits[, ExtraHitsMelee])`, qui AJOUTE la stat `ExtraHits` du caster -- que ce playbook
        n'ajoute pas. Meme ecart, meme correctif que `_stikkbomb_inputs` /
        `_mass_driver_accelerator_inputs` / `_ramming_speed_inputs`.
      * `base` : pour **1035**, AUCUN override -- `d1` y est `MinMaxDamageAverage` nue, et c'est
        exactement ce que rend `ab.get_damage()` (1035 est au registre (a)
        `_A_VIA_GET_DAMAGE_AMOUNT_MAIN`). Poser un override serait dupliquer le foyer.
        Pour **1093**, override = `GetDamage1` evaluee, c.-a-d. l'avg DOUBLEE quand la cible
        principale porte `Summon`. Hors ce cas la valeur est identique a `ab.get_damage()` (1093
        est au registre (a) `_A_VIA_OWN_ABILITY_BODY`, dont l'inscription reste JUSTE : les DEUX
        branches du `If` passent par `MinMaxDamageAverage`).
      * `profil` : aucun override (cf. l'en-tete du module -- les deux chemins natifs rendent la
        `damageProfile` de la config, `Psychic` pour les deux abilities).

    Contexte DSL indisponible (scene sans caster) -> on garde le seul `hits`, et la vague 1 retombe
    sur `ab.get_damage()` : sous-prediction NOMMEE sur une cible `Summon`, jamais une valeur
    inventee."""
    out: dict = {}
    if cfg is None or ab is None:
        return out
    hits = int((cfg.constants or {}).get(HITS_CONST) or 0)
    if hits:
        out["hits_override"] = hits
    if int(ab.ability_type) == MORTARIONS_PLAGUE_WIND:
        dctx = dsl_context(scene, caster_id, target_id)
        if dctx is not None:
            base = _wave_base(int(ab.ability_type), ab, cfg, 0, dctx)
            if base > 0:
                out["base_override"] = base
    return out


def wave_events(scene, caster_id: int, target_id, ability_id: int, ability_name: str,
                attack_pos, ab, cfg) -> list:
    """Batchs 2 et 3 : `AddRange(GenerateMultiHitAttackPredictions(..., t2, d2, ...))` puis
    `AddRange(... t3, d3 ...)`.

    Un event PAR ENTITE rendue par le selecteur de la vague (`TargetsSelector$$SelectUniqueUnits`,
    index 4 de l'interface), portant sur CETTE entite -- contrairement au quirk Stikkbomb/
    PlasmaGrenade, ou le `param_5` est `<Target>` et ou tous les events retombent sur la cible.
    Ici `param_5` est bien la vague, donc chaque unite recoit sa propre prediction contre SES PV,
    SON armure et SES modificateurs de defenseur.

    `t3` est reconstruit a partir de `t2` a chaque evaluation (aucun `Cache` sur la face DECISION,
    cf. `plague_wind_wave_selectors`) : les deux vagues sont donc lues sur le MEME etat, et leur
    disjonction (`- t1 - t2`) est structurelle, pas temporelle.

    ⚠ AUCUN filtre sur la cible principale ici, et c'est VOULU. L'exclusion est portee par les
    SELECTEURS eux-memes -- `AdjacentUnits(origin)` = `Units(AdjacentTiles(origin), ...) - origin`
    retire la cible de `t2`, et `t3` la retranche explicitement. Ajouter un `if tid == target_id:
    continue` serait une garde DEFENSIVE : elle ne changerait rien au regime natif (le natif
    emettrait l'event, lui) et MASQUERAIT un bug de selecteur au lieu de le faire remonter en
    desaccord avec `aiPlaybookPredict`.

    Config ou contexte manquants -> `[]` (degradation fidele, aucun event invente), meme convention
    que `_ramming_speed_self_events` / `_frenzied_firing_inputs`."""
    if cfg is None or ab is None:
        return []
    hits = int((cfg.constants or {}).get(HITS_CONST) or 0)
    if not hits:
        return []
    dctx = dsl_context(scene, caster_id, target_id)
    if dctx is None or dctx.target is None:
        return []

    _t1, t2, t3 = plague_wind_wave_selectors()
    events: list = []
    for wave, sel in ((1, t2), (2, t3)):
        base = _wave_base(int(ability_id), ab, cfg, wave, dctx)
        if base <= 0:
            continue
        for u in sel.evaluate(dctx):
            tid = (u or {}).get("id")
            if tid is None:
                continue
            dp = generate_multi_hit_attack_prediction(
                scene, caster_id, tid, ability_id, ability_name, attack_pos=attack_pos,
                base_override=base, hits_override=hits)
            if dp is not None:
                events.append(ProbableDamageEvent(target=tid, prediction=dp))
    return events
