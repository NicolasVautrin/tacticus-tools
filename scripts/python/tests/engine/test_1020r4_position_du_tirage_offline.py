"""#1020-r4 -- la POSITION du chokepoint `On(0x39 = EventTriggerType.PreDamageTaken)` dans le flux
PRNG. Purement OFFLINE (aucun runner).

Ce que #1020 avait deja rendu juste : la GRANULARITE (une emission par COUP, pas par groupe).
Ce que ce cliquet garde : sa POSITION. Le chokepoint doit etre joue DANS la boucle de coups,
entre la resolution d'un coup et le tirage du suivant -- pas apres toute la salve.

LU (build `rnca9r7q6c`) :

  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` boucle `while (i < numHits)` sur
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, suivi de
    `IdunBattle.Operations.ADamageOperation$$UpdateHitGroupAfterHit` et
    `$$UpdateCurrentAttackAfterHit` : un coup est INTEGRALEMENT resolu avant que le suivant ne
    tire quoi que ce soit ;
  * dans `ExecuteHit`, `IdunBattle.Core.HitDamage$$GetDamage` (la valeur) precede la
    sous-operation de split, elle-meme suivie d'
    `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` ;
  * l'emission d'`On(0x39)` vit dans `IdunBattle.Operations.ApplyDamageOperation$$Execute`, dont
    `IdunBattle.Core.Services.OperationProcessor$$ApplyDamage` est le SEUL appelant (xref unique).

D'ou l'entrelacement natif `[valeur i][trigger i][valeur i+1][trigger i+1]...`, mesure en live par
`probe_1020_savior_protocols_live.py` : avec transfert, les montants natifs des coups 2+ CHANGENT
(`250, 314, 275` -> `272, 216`), ceux d'un port par-groupe non.

Le TEMOIN de ces etages n'est pas nul par construction : le `_SinkTireur` consomme un tirage a
chaque coup, donc un port qui emettrait apres la salve rendrait des valeurs de coup IDENTIQUES au
run sans sink -- et c'est exactement ce que les etages 1 et 2 refusent.
"""
import ast
import pathlib

import pytest

from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.damage_hits import HitDamage
from engine.runner.prng import IntBasedMersenneTwister

_OPS = pathlib.Path(__file__).resolve().parents[2] / "engine" / "runner" / "operations"

#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    # VIDE, et c'est un RESULTAT : `--proposer` mesure 637 modules de fermeture d'imports pour
    # 638 chemins de cascade DERIVEE -- tout ce que ce fichier lit y tient deja, et #531 interdit
    # de recopier ce que le foyer derive.
    "chemins": (),
    "build": False,          # aucune lecture du binaire ni de `data/symbols/**`
    "toujours": False,
    "raison": (
        "Ce fichier garde la POSITION du chokepoint `On(0x39 = EventTriggerType.PreDamageTaken)` "
        "dans le flux PRNG, et les SIX foyers qui la determinent sont TOUS dans sa fermeture "
        "d'imports : la boucle qui appelle le sink (`operations/damage_hits.py`), le corps du "
        "chokepoint et son foyer de lecture (`operations/damage.py`), les quatre call-sites "
        "moteur qui le threadent (`damage_ops/{normal,ability,normal_like}.py`, "
        "`operations/additional_hits.py` -- atteints par l'etage 5, qui les LIT a l'AST), et le "
        "PRNG dont l'etage 1 DERIVE ses couts (`runner/prng.py`). Rien a declarer en plus : il "
        "n'y a aucune entree `data/**` ni aucun artefact hors import."),
}


class _SinkTireur:
    """Un consommateur de `On(0x39)` qui TIRE -- mirror minimal du `Maybe` de `SaviorProtocols`.

    Il enregistre, a chaque coup, le nombre de tirages deja consommes AVANT son propre tirage :
    c'est l'observable qui separe « joue dans la boucle » de « joue apres la salve »."""

    def __init__(self, rng, consomme=None):
        self.rng = rng
        self.consomme = set(consomme or ())     # index de coup dont le pending est CONSOMME
        self.avant = []                         # `call_count` a l'entree de chaque appel
        self.recus = []                         # `(health, shield)` demandes
        self.kept_health = self.kept_shield = self.transfers = 0

    def __call__(self, health: int, shield: int):
        idx = len(self.recus)
        self.avant.append(self.rng.call_count)
        self.recus.append((int(health), int(shield)))
        self.rng.next_bool(50)                  # LE tirage du trigger (1 `genrand_int32`)
        if idx in self.consomme:
            self.transfers += 1
            return None                         # pending CONSOMME -> coup transfere
        self.kept_health += int(health)
        self.kept_shield += int(shield)
        return int(health), int(shield)

    def cumul(self) -> tuple:
        """MEME contrat que `damage._PreDamageTakenSink.cumul` : le cumul vit sur le SINK, jamais
        dans le retour de `_run_hits` (cf. l'etage `LE CONTRAT DE SORTIE` plus bas)."""
        return (self.kept_health, self.kept_shield, self.transfers)


def _run(hits: int, sink=None, seed: int = 777, **kw) -> tuple:
    rng = IntBasedMersenneTwister(seed)
    if sink is not None:
        sink.rng = rng
    n0 = rng.call_count
    r = AttackDamageOperation._run_hits(rng, HitDamage(100, 200), HitDamage(100, 200), 0, False,
                                        hits, None, pending_sink=sink, **kw)
    return r, rng.call_count - n0


# ---------------------------------------------------------------- etage 1 : L'ENTRELACEMENT

def _couts() -> tuple:
    """`(cout d'un coup, cout du sink)` MESURES, jamais codes en dur.

    Une premiere version de cet etage avait ecrit « 1 tirage par coup » : faux (le mode ATTACK en
    consomme 2 -- la valeur plus le resolve slot 8 d'
    `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`), et `next_bool` en
    consomme 2 lui aussi. Un attendu code en dur y aurait fait accuser le PORT au lieu de la
    PREMISSE. On derive donc les deux couts du montage lui-meme, et on verifie que le cout d'un
    coup est CONSTANT (sinon l'arithmetique de l'etage ne veut rien dire)."""
    c1 = _run(1, None)[1]
    c4 = _run(4, None)[1]
    assert c1 > 0 and c4 == 4 * c1, (
        "le cout d'un coup n'est pas constant (%d pour 1 coup, %d pour 4) -- l'attendu de cet "
        "etage n'aurait plus de sens" % (c1, c4))
    cs = _run(1, _SinkTireur(None))[1] - c1
    assert cs > 0, "le sink ne consomme AUCUN tirage : le temoin de cet etage serait DEGENERE"
    return c1, cs


def test_le_trigger_tire_ENTRE_deux_valeurs_de_coup():
    """LE cran. Avec un sink qui tire, le natif intercale `[coup0][t0][coup1][t1]...`.

    Le sink d'index k doit donc voir `(k+1) * cout_coup + k * cout_sink` tirages deja consommes.
    Un port qui emettrait APRES la salve les verrait tous a `4 * cout_coup + k * cout_sink` --
    c'est la forme exacte du defaut de position."""
    c_coup, c_sink = _couts()
    sink = _SinkTireur(None)
    r, n = _run(4, sink)
    assert len(sink.avant) == 4, "un appel par coup attendu, vu %r" % (sink.avant,)
    attendu = [(k + 1) * c_coup + k * c_sink for k in range(4)]
    par_groupe = [4 * c_coup + k * c_sink for k in range(4)]
    assert attendu != par_groupe, "montage DEGENERE : les deux hypotheses de position coincident"
    assert sink.avant == attendu, (
        "le trigger n'est PAS joue entre deux coups (tirages vus a l'entree : %r ; attendu %r). "
        "Un port PAR GROUPE rendrait %r." % (sink.avant, attendu, par_groupe))
    assert n == 4 * (c_coup + c_sink)
    assert sink.cumul() != (0, 0, 0), "le sink n'a rien cumule : le temoin serait DEGENERE"
    assert "pre_damage_taken" not in r, "le cumul a fuite dans le CONTRAT DE SORTIE du canal"


def test_le_tirage_du_trigger_DEPLACE_les_coups_suivants():
    """Consequence observable, et c'est celle que le live mesure : le coup 0 est INCHANGE (le
    trigger tire APRES lui), les coups 1+ DIVERGENT. Un port par-groupe les laisserait identiques
    -- c'est le temoin NON NUL de cet etage."""
    a, _ = _run(4, None)
    b, _ = _run(4, _SinkTireur(None))
    assert a["per_hit"][0] == b["per_hit"][0], \
        "le coup 0 a bouge : le trigger tire AVANT lui, ce que le natif ne fait pas"
    assert a["per_hit"][1:] != b["per_hit"][1:], (
        "les coups 1+ sont IDENTIQUES au run sans trigger (%r) : le tirage du trigger n'a pas "
        "ete intercale -- c'est le defaut de position de #1020-r4" % (a["per_hit"],))


# ---------------------------------------------------------------- etage 2 : LE PENDING CONSOMME

def test_un_pending_consomme_sort_en_transfert_et_non_en_kept():
    """`IdunBattle.Operations.TransferDamageOperation$$GetDamage` ECRIT `comp+0x64 = 0` : la
    relecture `System.Nullable<T>$$GetValueOrDefault` rend alors la struct ZERO. Le coup ne doit
    donc RIEN laisser dans `kept_health`, et etre compte comme transfere."""
    sink = _SinkTireur(None, consomme=(1, 3))
    r, _ = _run(4, sink)
    kept_h, kept_s, transferts = sink.cumul()
    assert transferts == 2, "2 coups consommes attendus, vu %d" % transferts
    attendu = sum(h for i, (h, _s) in enumerate(sink.recus) if i not in (1, 3))
    assert kept_h == attendu, (
        "`kept_health` = %d, attendu %d (la somme des SEULS coups non consommes)" % (kept_h, attendu))
    assert kept_h < sum(h for h, _s in sink.recus), \
        "aucun degat n'a ete retire a la victime : le transfert serait un BONUS, pas un DEPLACEMENT"
    assert kept_s == 0


def test_sans_sink_le_chokepoint_de_groupe_garde_la_main():
    """NON-REGRESSION. `pending_sink=None` (DoT, knockback, degat direct, et tout appelant hors des
    quatre call-sites moteur) : aucun sink, donc `AttackDamageOperation.pre_damage_taken_of` rend
    `None`, donc `_apply_damage_pipeline` emet lui-meme via `_pre_damage_taken_per_hit`, et le flux
    PRNG est celui d'avant."""
    c_coup, _ = _couts()
    r, n = _run(4, None)
    assert AttackDamageOperation.pre_damage_taken_of(None) is None
    assert n == 4 * c_coup, "les 4 coups et RIEN d'autre attendus, vu %d" % n
    assert len(r["per_hit_pending"]) == 4, "la decomposition par coup reste publiee"


# ---------------------------------------------------------------- etage 3 : LE SITE (A)

def test_une_cible_deja_overkillee_n_emet_RIEN():
    """SITE (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` : `HasFlag(target, 8 =
    Overkilled)` fait `return` AVANT l'ecriture du pending, donc avant l'emission. Le sink ne doit
    JAMAIS etre appele -- et ne doit donc consommer AUCUN tirage."""
    c_coup, _ = _couts()
    sink = _SinkTireur(None)
    r, n = _run(4, sink, overkilled0=True, hp_current=1000)
    assert sink.avant == [], "le chokepoint a emis sur une cible deja overkillee"
    assert n == 4 * c_coup, (
        "le trigger a consomme des tirages malgre le SITE (A) (%d au lieu de %d) -- les coups "
        "s'executent, seul le pending est supprime" % (n, 4 * c_coup))
    assert sink.cumul() == (0, 0, 0)


# ------------------------------------------- etage 4 : LE CONTRAT DE SORTIE N'EST PAS ELARGI

def test_le_retour_de_run_hits_est_IDENTIQUE_avec_et_sans_sink():
    """LE cran de la REGRESSION que cette tranche a REELLEMENT causee, puis corrigee.

    Un premier jet publiait le cumul sous une cle `pre_damage_taken` du dict rendu par
    `_run_hits`. Ce dict est le CONTRAT DE SORTIE du canal : plusieurs harnais SUBSTITUENT
    `_run_hits` par un stub qui le rend en entier, et lire une cle de plus les fait lever
    `KeyError`. Deux gardes EXISTANTES l'ont attrape --
    `tests/engine/runner/test_failed_block_attack_scope_offline.py::
    test_execute_additional_hits_CHAINE_l_etat_de_groupe_en_groupe` et
    `tests/test_additional_hits_variant_signatures_offline.py::
    test_toute_substitution_expose_le_contrat_de_SORTIE`.

    Elles ne peuvent pas voir la faute AVANT qu'elle atteigne `additional_hits` ; ce cran-ci la
    voit a la SOURCE, sur le canal lui-meme. Le cumul appartient au SINK, qui le produit."""
    avec, _ = _run(4, _SinkTireur(None))
    sans, _ = _run(4, None)
    assert set(avec) == set(sans), (
        "le retour de `_run_hits` DEPEND du sink (cles en plus avec sink : %s ; en moins : %s) -- "
        "toute substitution du canal restee en arriere levera `KeyError`"
        % (sorted(set(avec) - set(sans)), sorted(set(sans) - set(avec))))
    assert "pre_damage_taken" not in avec, (
        "le cumul `pre_damage_taken` est publie dans le CONTRAT DE SORTIE du canal -- il doit "
        "vivre sur le SINK (`damage._PreDamageTakenSink.cumul`)")


def test_le_cumul_se_lit_par_le_FOYER_unique():
    """`AttackDamageOperation.pre_damage_taken_of` est le seul point de lecture : `None` sans sink
    (repli sur le chokepoint de groupe), le cumul sinon. Les quatre call-sites moteur passent par
    lui -- l'etage 5 le verifie a l'AST."""
    assert AttackDamageOperation.pre_damage_taken_of(None) is None
    sink = _SinkTireur(None)
    _run(4, sink)
    assert AttackDamageOperation.pre_damage_taken_of(sink) == sink.cumul() != (0, 0, 0)


# ---------------------------------------------------------------- etage 5 : LE CABLAGE

def _arbre(rel):
    return ast.parse((_OPS / rel).read_text(encoding="utf-8"))


def _appels_run_hits(arbre):
    return [n for n in ast.walk(arbre)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_run_hits"]


_VECTEURS = ("damage_ops/normal.py", "damage_ops/ability.py", "damage_ops/normal_like.py",
             "additional_hits.py")


@pytest.mark.parametrize("rel", _VECTEURS)
def test_chaque_vecteur_moteur_threade_son_sink(rel):
    """Un vecteur qui ne threade PAS `pending_sink` retombe silencieusement sur l'emission par
    groupe : ni erreur, ni crash, juste un flux PRNG desaligne des le 2e coup. C'est exactement la
    forme de degradation que #1020-r4 corrige, donc elle doit etre gardee explicitement."""
    appels = _appels_run_hits(_arbre(rel))
    assert appels, "%s : aucun appel a `_run_hits`" % rel
    for appel in appels:
        noms = {k.arg for k in appel.keywords if k.arg}
        assert "pending_sink" in noms, (
            "%s : `_run_hits` appele SANS `pending_sink` -- l'emission `On(0x39)` retombe au "
            "chokepoint de groupe, donc apres toute la salve" % rel)


@pytest.mark.parametrize("rel", _VECTEURS)
def test_le_sink_et_le_pipeline_partagent_le_meme_isFirstDamagingHit(rel):
    """`isFirstDamagingHit` (`DamageAppliedResult+0x18`) est consomme par le sink ET declare au
    chokepoint. Deux expressions independantes derivant en silence est precisement le defaut que
    #963-r2 a coute : on exige donc que les deux viennent du MEME nom local."""
    arbre = _arbre(rel)
    sinks = [n for n in ast.walk(arbre)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "make_pre_damage_taken_sink"]
    assert sinks, "%s : aucun `make_pre_damage_taken_sink`" % rel
    # Seuls les appels dont l'emission a DEJA ete jouee (`pre_damage_taken`) sont concernes : le
    # meme fichier peut aussi porter un vecteur DIRECT (`normal_like.execute_direct`), qui n'a ni
    # coups ni sink et emet legitimement au chokepoint de groupe.
    pipes = [n for n in ast.walk(arbre)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "_apply_damage_pipeline"
             and any(k.arg == "pre_damage_taken" for k in n.keywords if k.arg)]
    assert pipes, "%s : aucun appel au chokepoint portant `pre_damage_taken`" % rel
    assert len(pipes) == len(sinks), (
        "%s : %d sink(s) pour %d chokepoint(s) recevant le cumul -- un sink dont le cumul n'est "
        "pas THREADE fait EMETTRE DEUX FOIS (le pipeline re-deroule alors `per_hit_pending`)"
        % (rel, len(sinks), len(pipes)))

    def _noms(call, arg):
        kw = {k.arg: k.value for k in call.keywords if k.arg}
        assert arg in kw, "%s : `%s` absent" % (rel, arg)
        return {n.id for n in ast.walk(kw[arg]) if isinstance(n, ast.Name)}

    n_sink = set()
    for s in sinks:
        n_sink |= _noms(s, "is_first_damaging_hit")
    for p in pipes:
        assert _noms(p, "is_first_damaging_hit") & n_sink, (
            "%s : le chokepoint et le sink declarent `isFirstDamagingHit` par des expressions "
            "SANS nom commun -- elles deriveront" % rel)
