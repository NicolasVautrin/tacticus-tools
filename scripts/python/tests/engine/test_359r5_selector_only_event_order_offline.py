"""#359-r5 -- l'ORDRE des `ProbableDamageEvent`, et le registre qui dit QUELS playbooks n'ont pas de
batch `<Target>`.

Ce fichier garde l'etage AU-DESSUS de `test_359r2_hades_sort_by_row_offline.py` : celui-la teste le
SELECTEUR (`GetAllTargets` et son tri), celui-ci teste ce que `make_damage_predictions` en EMET.

CE QUE LE DECOMPILE DIT. Il y a DEUX formes de `<Ability>Playbook$$MakeDamagePredictions`, et rien
d'autre que le corps natif ne permet de les distinguer :

  A. AUCUN event pour `<Target>` separement. La cible n'a un event que si le selecteur la porte, et
     alors A SA PLACE. Cette forme se presente sous DEUX ecritures, qui different par l'ENDROIT ou
     la boucle est ecrite -- et qui sont OBSERVATIONNELLEMENT LA MEME CHOSE :

     A1. la boucle est DANS le `MakeDamagePredictions` : `GetEntitiesFromSelector(<sel>, caster,
         casterPosition, target)` puis, par entite, `GenerateMultiHitAttackPredictions(..., pvVar10,
         Entity(pvVar10), ...)` + `AddRange`.

         `IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$MakeDamagePredictions`   (1147)
         `IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$MakeDamagePredictions`   (1148)
         `IdunBattle.AI.Playbook.MurderousSwingPlaybook$$MakeDamagePredictions`          (1137)

         (celui de 1137 ne CONSOMME meme pas son argument `target` : il boucle sur
         `AdjacentEnemies(caster)` et compte `Enumerable.Count(entities)` pour `GetCorrectDamage`.)

     A2. UN SEUL appel a la surcharge PLURIELLE, a qui on passe le SELECTEUR : la boucle vit alors
         dans le generique
         `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateAttackPredictions`
         (RELU : il evalue la formule de degat UNE fois, `Select`e le selecteur, puis emet un
         `IdunBattle.AI.Playbook.ProbableDamageEvent` PAR entite ; l'argument `target` ne sert qu'a
         construire les `AbilityEntities`, il n'emet AUCUN event a lui seul).

         `IdunBattle.AI.Playbook.Loki.TacticalPrecisionPlaybook$$MakeDamagePredictions`  (1154)
         `IdunBattle.AI.Playbook.Loki.ExplosivePresentsPlaybook$$MakeDamagePredictions`  (1170)

  B. BATCH `<Target>` EXPLICITE, puis une boucle sur un SECOND selecteur :

         `IdunBattle.AI.Playbook.Loki.HarvesterOfSoulsPlaybook$$MakeDamagePredictions`
         `IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions`
         `IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions`
         `IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$MakeDamagePredictions`
         `IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$MakeDamagePredictions`

POURQUOI UN REGISTRE ET PAS UNE DEDUCTION. On serait tente de deriver la forme dynamiquement
(<< le set contient-il la cible ? >>). C'est FAUX : `FrenziedFiring` a un batch `<Target>` explicite
ET un selecteur (`AdjacentEnemies(TargetTile())`) qui peut contenir des membres quelconques. La
forme est une propriete du CORPS NATIF, pas de la donnee -- elle se lit, elle ne se devine pas.

CE QUE CE FICHIER NE PROUVE PAS : que le SCORE change. Il ne change pas -- le consommateur du terme
degat SOMME (`...ComparablePlaybook...$$CalculateUtilityFromPredictions`). C'est precisement ce qui
rend l'ecart INVISIBLE, et donc ce qui justifie un garde ecrit sur l'ORDRE et pas sur une utilite.

DECLENCHEUR ci-dessous : `chemins` VIDE, mesure de `probe_486r15 --proposer`.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": True,
    "raison": "`chemins` VIDE : `probe_486r15 --proposer` mesure que la fermeture d'imports de ce "
              "fichier tient ENTIEREMENT dans la cascade derivee du foyer, qu'on ne redeclare pas "
              "(#531). Un perimetre vide avec `toujours: False` ne serait JAMAIS rejoue, d'ou "
              "`toujours: True` -- le fichier est offline et court (aucun runner, prediction "
              "substituee par une sentinelle). Ce qu'il garde le justifie : l'appartenance au "
              "registre `_MAKE_DMG_SELECTOR_ONLY` est une lecture de DECOMPILE, et s'y tromper est "
              "SILENCIEUX (l'ensemble des events et leurs valeurs sont identiques, seul l'ordre "
              "bouge, et le consommateur SOMME). `build: False` : rien n'est fige depuis le "
              "binaire, c'est le texte des citations qui tient la classification.",
}

import pytest

import engine.playbook.prediction.abilities as PA
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.unit_context import UnitContext

_HADES = int(ActiveAbilityType.HadesAutocannons)     # 1147
_HADES_NAME = "HadesAutocannons"
_RANGE_FALLBACK = 2

#: Les cinq playbooks de FORME B, cites plus haut. Ils DOIVENT rester hors du registre : leur
#: appliquer la forme A supprimerait leur batch `<Target>`, donc un event entier.
_FORME_B = (ActiveAbilityType.HarvesterOfSouls, ActiveAbilityType.PlasmaCannon,
            ActiveAbilityType.FrenziedFiring, ActiveAbilityType.MassDriverAccelerator,
            ActiveAbilityType.FragBomb)


class _Rec:
    """Sentinelle de prediction -- `make_damage_predictions` n'en lit que `will_be_kill()`."""

    def will_be_kill(self) -> bool:
        return False


class _Scene:
    """Scene MINIMALE : juste ce que `make_damage_predictions` interroge pour 1147.

    Rows 6 / 3 / 5 pour les summons non-cibles et 4 pour la cible -- MEMES positions que
    `test_359r2_hades_sort_by_row_offline.py`, pour que l'ordre attendu se lise contre le meme
    montage. La cible est en position MEDIANE du tri : c'est ce qui rend le test discriminant (en
    tete ou en queue, les deux regimes coincideraient)."""

    def __init__(self):
        self.units = [self._u(1, team=1, pos=(0, 0), summon=False),   # caster
                      self._u(10, team=2, pos=(3, 4), summon=True),   # CIBLE, row 4
                      self._u(11, team=2, pos=(3, 6), summon=True),   # row 6
                      self._u(12, team=2, pos=(3, 3), summon=True),   # row 3
                      self._u(13, team=2, pos=(3, 5), summon=True)]   # row 5
        self.elev_by_pos = {}
        self.tile_effects_by_pos = {}
        self.board = None
        self.machine_of_war_position = None
        # `_entity_traits` (foyer unique de la face prediction, #267-r1) lit `scene.vis_by_id` puis
        # `entity_trait_names(ctx, vis)`. `traits_measured = True` = le canal MESURE, exactement le
        # regime d'une bataille live -- pas une reconstruction depuis un kit gameconfig. ⚠ Le
        # substrat d'`UnitContext.traits` est un ensemble de NOMS, pas d'ids : poser l'ordinal y
        # rend un ensemble que `has_trait` ne reconnait pas, SANS LEVER (le volet AoE devient
        # simplement muet -- c'est ce que ce montage a d'abord mesure).
        self.vis_by_id = {u["id"]: "necroSpyder" for u in self.units}
        self._ctx = {u["id"]: UnitContext(entity_id=u["id"],
                                          traits=[UnitTrait.Summon.name] if u["traits"] else [],
                                          traits_measured=True) for u in self.units}

    @staticmethod
    def _u(uid, team, pos, summon):
        return {"id": uid, "team": team, "pos": {"col": pos[0], "row": pos[1]}, "alive": True,
                "hp": 100, "hpMax": 100, "ctrl": (team == 1),
                "traits": [int(UnitTrait.Summon)] if summon else []}

    def ctx(self, uid):
        return self._ctx.get(int(uid))

    def ability_state(self, uid, aid):
        return {"level": 1, "multiplier": 100}

    def pos(self, uid):
        u = next((x for x in self.units if x["id"] == int(uid)), None)
        return None if u is None else (u["pos"]["col"], u["pos"]["row"])

    def hp(self, uid):
        return 100

    def hpmax(self, uid):
        return 100


def _order(monkeypatch, ability_id=_HADES, name=_HADES_NAME):
    """Ordre des `targetId` que `make_damage_predictions` fait predire, dans l'ordre d'appel."""
    seen = []

    def _fake(scene, uid, tgt, aid, aname, attack_pos=None, base_bonus=0,
              base_override=None, hits_override=None, profile_override=None):
        seen.append(tgt)
        return _Rec()

    monkeypatch.setattr(PA, "generate_multi_hit_attack_prediction", _fake)
    evs = PA.make_damage_predictions(_Scene(), 1, 10, ability_id, name)
    return seen, evs


# ────────────────────────────── 1. le montage discrimine-t-il ? ─────────────────────────────────

def test_le_montage_est_discriminant_avant_toute_assertion_d_ordre():
    """ANTI-VACUITE. Si le selecteur ne rendait qu'UNE entite (ou zero), tout ordre serait vrai et
    les tests suivants passeraient sans rien prouver -- exactement le vice que #270-r1-r1-r3 a
    trouve sur un ensemble d'ordinaux vide. On exige donc >= 3 membres ET la cible en position
    NI premiere NI derniere."""
    import gameconfig as GC
    rng = (GC.ability(_HADES_NAME) or {}).get("constants", {}).get("range")
    assert rng is not None and int(rng) >= _RANGE_FALLBACK, (
        "le `range` gameconfig de 1147 (%r) ne couvre plus le montage (rows 3..6 autour de la row "
        "4) : les summons sortent du disque et le test ne discrimine plus rien" % (rng,))


def test_1147_emet_la_cible_A_SA_PLACE_TRIEE_pas_en_tete(monkeypatch):
    """LA MESURE QUE #359 AVAIT PRISE, reproduite offline. Le natif rend `[113, 110, 116]` -- la
    cible `110` en 2e position, parce que `SurroundingUnits(..., includeCenter: 1)` l'a mise dans le
    selecteur et que `SortByRow` l'a classee. Le port l'extrayait et l'emettait en TETE."""
    seen, evs = _order(monkeypatch)
    assert len(seen) >= 3, "montage degenere : %r" % (seen,)
    assert seen[0] != 10, (
        "la cible (10) est encore emise en TETE (%r) : `make_damage_predictions` la traite toujours "
        "comme un batch principal alors que 1147 est dans `_MAKE_DMG_SELECTOR_ONLY`" % (seen,))
    assert 10 in seen, "la cible a DISPARU des events (%r) -- elle est dans le selecteur" % (seen,)
    assert [e.target for e in evs] == seen, (
        "l'ordre des events emis (%r) ne suit pas l'ordre des predictions demandees (%r)"
        % ([e.target for e in evs], seen))


def test_l_ordre_emis_EST_celui_du_selecteur(monkeypatch):
    """Pas seulement << pas en tete >> : l'ordre emis doit etre EXACTEMENT celui que rend
    `HadesAutocannonsAbility.get_aoe_targets`. Un test qui ne verifierait que la position de la
    cible resterait vert si la queue etait melangee."""
    from engine.dsl import nodes as dsl
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    from engine.entities.abilities.active_ability import HadesAutocannonsAbility
    import gameconfig as GC

    sc = _Scene()
    cfg = AbilityConfiguration.from_gameconfig(_HADES_NAME, GC.ability(_HADES_NAME))
    ab = HadesAutocannonsAbility(ability_type=_HADES, caster=UnitContext(entity_id=1), config=cfg,
                                 ability_state={"level": 1, "multiplier": 100})
    by = {u["id"]: u for u in sc.units}
    ctx = dsl.DslContext(units=sc.units, caster=by[1], target=by[10], config=cfg, ability_level=1,
                         has_trait=lambda u, t: int(t) in ((u or {}).get("traits") or []),
                         current_player_team=1)
    attendu = [u["id"] for u in ab.get_aoe_targets(ctx)]
    seen, _ = _order(monkeypatch)
    assert seen == attendu, (
        "events %r != selecteur %r -- l'etage d'emission REORDONNE ce que le selecteur a classe"
        % (seen, attendu))


def test_hors_du_registre_la_cible_REVIENT_en_tete(monkeypatch):
    """CONTRE-EPREUVE, et c'est elle qui prouve que le registre est le discriminant : on retire 1147
    du registre et le comportement d'AVANT revient (cible en tete, retiree de la queue). Sans ce
    test, un `_MAKE_DMG_SELECTOR_ONLY` devenu inerte (mal orthographie, vide) passerait inapercu --
    la forme A serait alors appliquee a personne, en silence."""
    monkeypatch.setattr(PA, "_MAKE_DMG_SELECTOR_ONLY", frozenset())
    seen, _ = _order(monkeypatch)
    assert seen and seen[0] == 10, (
        "hors registre, la cible devrait etre l'event PRINCIPAL, en tete : %r" % (seen,))
    assert seen.count(10) == 1, "la cible est emise deux fois : %r" % (seen,)


# ───────────────────────────────── 2. le REGISTRE lui-meme ──────────────────────────────────────

def test_le_registre_porte_les_playbooks_SANS_batch_Target():
    """L'ensemble EXACT, fige a la lecture. Toute entree/sortie doit venir d'une LECTURE du corps de
    `<Ability>Playbook$$MakeDamagePredictions`.

    ⚠ PREMISSE CORRIGEE (#10029). Ce test s'appelait `..._les_trois_playbooks_a_boucle_unique` et
    figeait un triplet : il est devenu ROUGE quand #976 (1154) puis #909-r7 (1170) ont inscrit deux
    playbooks de plus. Les DEUX corps ont ete RELUS sur le build courant, et les deux sont bien
    SANS batch `<Target>` -- mais en ECRITURE A2 (cf. l'en-tete), ce que le nom << a boucle unique >>
    ne decrivait pas : leur `MakeDamagePredictions` ne contient AUCUNE boucle, il delegue le
    selecteur a la surcharge plurielle. C'est le CRITERE qui etait mal nomme, pas le registre qui
    avait derive."""
    assert PA._MAKE_DMG_SELECTOR_ONLY == frozenset({
        ActiveAbilityType.HadesAutocannons,     # 1147  A1
        ActiveAbilityType.DaemonicOrdnance,     # 1148  A1
        ActiveAbilityType.MurderousSwing,       # 1137  A1
        ActiveAbilityType.TacticalPrecision,    # 1154  A2 (#976)
        ActiveAbilityType.ExplosivePresents,    # 1170  A2 (#909-r7)
    }), ("le registre a bouge (%r). Toute entree/sortie doit venir d'une LECTURE du corps de "
         "`<Ability>Playbook$$MakeDamagePredictions` -- un batch `<Target>` explicite avant la "
         "boucle = FORME B = hors registre." % (sorted(int(x) for x in PA._MAKE_DMG_SELECTOR_ONLY),))


@pytest.mark.parametrize("aid", _FORME_B, ids=lambda a: a.name)
def test_les_playbooks_a_batch_TARGET_explicite_restent_HORS_du_registre(aid):
    """Les cinq contre-temoins. Les faire entrer supprimerait leur event `<Target>` -- une prediction
    ENTIERE en moins, la degradation la plus grave de cette famille."""
    assert aid not in PA._MAKE_DMG_SELECTOR_ONLY, (
        "%s (%d) a un batch `<Target>` EXPLICITE au decompile : elle ne peut pas etre dans "
        "`_MAKE_DMG_SELECTOR_ONLY`" % (aid.name, int(aid)))


def test_les_deux_familles_sont_NON_VIDES():
    """ANTI-VACUITE du registre : les deux cotes doivent porter du monde. Un registre VIDE ferait
    passer `test_hors_du_registre_la_cible_REVIENT_en_tete` (aucune forme A appliquee, donc la
    contre-epreuve devient le regime NOMINAL), et un registre qui contiendrait TOUTES les abilities
    ferait passer le premier lot mais pas ceux-la -- c'est l'asymetrie qu'on verrouille ici.

    ⚠ LE CARDINAL DU REGISTRE N'EST PLUS FIGE ICI (#10029), ET C'EST LE CORRECTIF. Ce test ecrivait
    `len(PA._MAKE_DMG_SELECTOR_ONLY) == 3`, donc il DOUBLAIT le cliquet d'egalite exacte ci-dessus :
    l'arrivee legitime de 1154 et 1170 a rendu DEUX tests rouges pour UNE seule cause, et le second
    n'apportait rien que le premier ne disait mieux (il ne nommait meme pas les entrees). Ce qui est
    garde ici, et qui n'est garde QUE ici, c'est la NON-VACUITE et la DISJONCTION -- deux proprietes
    qui ne se periment pas quand le registre grandit.

    Le `len(_FORME_B) == 5`, lui, RESTE : `_FORME_B` est une constante de ce fichier, et la vider
    ferait DISPARAITRE les cinq tests parametres ci-dessus sans qu'aucun rouge ne l'annonce (pytest
    ne collecte simplement plus rien -- l'angle mort de #455-r3)."""
    assert PA._MAKE_DMG_SELECTOR_ONLY, (
        "registre VIDE : la forme A n'est appliquee a personne, et la contre-epreuve "
        "`test_hors_du_registre_la_cible_REVIENT_en_tete` devient le regime nominal")
    assert len(_FORME_B) == 5, (
        "les contre-temoins ont ete amputes (%d) : les tests parametres ci-dessus disparaissent de "
        "la COLLECTE, sans rougir" % (len(_FORME_B),))
    assert not (set(_FORME_B) & set(PA._MAKE_DMG_SELECTOR_ONLY))


# ────────────────────────── 3. `nrEnemies` = Count(<le set du natif>) ────────────────────────────

def test_nrEnemies_de_MurderousSwing_est_la_TAILLE_DU_SET_pas_un_de_plus(monkeypatch):
    """`IdunBattle.AI.Playbook.MurderousSwingPlaybook$$MakeDamagePredictions` calcule

        nrEnemies = Enumerable.Count(entities)      # entities = AdjacentEnemies(caster)

    et le passe a `...MurderousSwingAbility$$GetCorrectDamage`, qui AJOUTE `extraDmg` a la base SI
    et SEULEMENT SI `nrEnemies == 1`. Le port ecrivait `1 + len(aoe)` avec `aoe` = set MOINS la
    cible : juste tant que la cible est DANS le set (le regime ordinaire d'une melee), faux d'un
    exactement quand elle n'y est pas -- et ce cas-la BASCULE la clause, donc la BASE du degat.

    On mesure le compte passe a `get_correct_damage`, pas une magnitude : c'est l'etage, pas le
    scalaire."""
    vus = []

    class _Ab:
        level, multiplier = 1, 100

        def get_damage(self):
            return 100

        def get_correct_damage(self, base, nr_enemies):
            vus.append(nr_enemies)
            return base

        def get_aoe_targets(self, ctx):
            # deux membres, dont la CIBLE (10) : c'est le regime melee ordinaire
            return [{"id": 10}, {"id": 11}]

        def get_max_secondary_targets(self):
            return None

        def get_prediction_set_repeat(self, n):
            return 1

        def get_health_to_lose(self, hpmax):
            return 0

    monkeypatch.setattr(PA, "active_ability_for", lambda *a, **k: _Ab())
    monkeypatch.setattr(PA, "generate_multi_hit_attack_prediction",
                        lambda *a, **k: _Rec())
    PA.make_damage_predictions(_Scene(), 1, 10, int(ActiveAbilityType.MurderousSwing),
                               "MurderousSwing")
    assert vus == [2], (
        "nrEnemies = %r, attendu 2 = Count(set) -- si c'est 3, le port compte encore "
        "`1 + len(aoe)` alors que 1137 est une BOUCLE UNIQUE sur son selecteur" % (vus,))
