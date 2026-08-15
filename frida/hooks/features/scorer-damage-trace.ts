    // Scorer / utility / damage-modifier TRACE TOOLKIT — capture, during a FRESH scoring pass, exactly what
// the native AI computes per attack candidate: scorer damage, JOINT (tile,target) utility, tile-term,
// tile-leaf outputs, composite children, damage bonuses. A reusable agreement-debugging kit (NOT a one-shot).
//
// ═══ CAPTURE RECIPE (post multi-runner refacto #43 — 3 gotchas, sinon buffer VIDE) ═════════════════════
// Le helper Python `scripts/python/scorer_trace_capture.py::capture(seed, want=...)` encapsule ce flux —
// s'en servir plutot que de le re-deriver. Les 3 gotchas :
//   1. Runner isole : `rl_duel build --state-file logs/runners/X.json` (ROOT-ANCHORED ; `data/` est
//      VERSIONNE et REFUSE par rl_duel depuis #349 -- les sorties de run vont dans `logs/`) ; le runnerId
//      se lit DANS ce fichier JSON, pas dans stdout.
//   2. Traces = OriginBuffers PAR ORIGINE (#43, purge au dispose) : dumper avec `{runnerId: rid}`. Les RPC
//      ai-step posent `setTraceOrigin(runnerId)` ; sans le bon filtre le dump revient vide (hooks OK quand meme).
//   3. Les hooks (ctor + AllMods) ne firent que quand l'IA native SCORE vraiment (tour joué :
//      `aiStepDryRun`, ou l'`endturn` d'un joueur IA). `aiStepDryRun` ne score que l'action CHOISIE
//      (si l'IA choisit un move => AUCUN ctor d'attaque). Le `decisionView` du drive NE suffit PAS a
//      lui seul (chemin de prediction d'AFFICHAGE, + CachedDamagePrediction). => activer
//      `scorerDamageTraceOn` AVANT que le scenario tourne (p.ex. avant le drive) ET capter sur les
//      tours REELLEMENT joués. OBSERVE : un drive skewe vers les attaques ENNEMIES (scorees pendant
//      leurs endturn) ; capter l'attaque d'une unite AMIE precise demande que l'IA CHOISISSE cette
//      attaque (positionner pour que ce soit son meilleur coup). L'ancienne mention « during
//      aiStepDryRun » n'etait pas fausse mais incomplete (endturn IA score aussi).
// ═════════════════════════════════════════════════════════════════════════════════════════════════════
//
// ═══ ⚠ BUILD-SPECIFIC RVA HOOKS — REFRESH FROM DUMP ON EVERY HASH CHANGE ═══════════════════════════════
// TROIS hooks résolvent proprement d'un build à l'autre : `ProbableDamageEvent..ctor` (findMethod — le dégât
// du scorer, auto-armé au register), plus `CalculateActionUtility` et `CalculateUtilityFromTilePrediction`
// depuis #259-b — leurs corps pleinement partagés se lisent sur le MethodInfo de l'instance INFLATÉE
// (`resolveSharedPlaybookBody`, mesuré par `probe_262_gshared_runtime.py`). Elles n'ont PLUS d'adresse en dur.
// Le RESTE (itérateurs ElevationUtility / tile-leaf, ComposedUtility.MoveNext, GetMultiplierFromDamageBonus)
// reste hooké par adresse en dur, valable pour le hash `t6dpr4k06g` UNIQUEMENT.
// ⚠ Ces cas-là ne sont PAS de même nature : ce sont des ITÉRATEURS et des corps sans classe porteuse
// atteignable — la recette « remonter au parent inflaté » ne s'y applique pas telle quelle. Ne pas
// généraliser #259-b sans re-mesurer cible par cible.
// On the next build these RVAs point to RANDOM code and Interceptor.attach would corrupt it, so they are
// ARMED LAZILY by `scorerDamageTraceOn` (installRvaHooks), NEVER auto-attached at register. Before re-arming
// on a new build: refresh every RVA_* constant + LEAF_HOOKS_VA from the fresh dump (search_symbols_by_name on
// the class → VA − 0x180000000, computed in code). cf. feedback_rva_transcription_from_va.
// ═════════════════════════════════════════════════════════════════════════════════════════════════════
//
// Choke point: `ProbableDamageEvent..ctor(IEntity target, DamagePredictionResult
// damagePrediction, Nullable<Fix64> probability, Nullable<Fix64> weight)` — EVERY
// playbook's MakeDamagePredictions (vtable+0x358) builds its events through this
// ctor. Hooking it passively during `aiStepDryRun` records exactly the (target,
// min/max health damage, hits) the scorer used per candidate — with CrushingStrike
// / Terrifying / all attacker+defender modifiers applied by the native.
//
// Struct RE-DERIVE sur `rnca9r7q6c` (#276) — les anciens offsets etaient ceux de `gqfc5mff6c`
// et rendaient du garbage silencieux (cf. `docs/rl/case-268-decodeur-prediction-perime.md`) :
//   ProbableDamageEvent (0xb8) { IEntity Target@0x0; DamagePredictionResult DamagePrediction@0x8;
//                                Fix64 Probability@0xa8; Fix64 Weight@0xb0 }
//   DamagePredictionResult (0xa0) : table complete + preuve par champ dans
//     `frida/hooks/game/damage-prediction.ts`. Ce fichier n'ecrit plus aucun offset.
//   IEntity : id@+0x10 (BEntityId 4B), type@+0x14 (EntityType).
//
// Gated by `trace.on` (default OFF — the ctor also fires during live game AI). The findMethod ctor hook is
// auto-armed at register (buffer gated); the RVA hooks arm on first `scorerDamageTraceOn`.
// RPC: scorerDamageTrace{On,Off,Clear,Dump} + scorer{Util,TileTerm,Elev,Leaf,Bonus}TraceDump + scorerComposedDump.

import { Ctx } from "../controller.js";
import {
    findClassAnywhere, findMethod, il2cppBase, class_get_name, s, class_get_parent,
} from "../il2cpp/helpers.js";
import { pinnedAddress, PinnedAddress, installedBuild } from "../il2cpp/build-pin.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { log } from "../runtime/diag.js";
import { getTraceOrigin, OriginBuffers } from "../game/trace-origin.js";
import { arm, disarm, capturing, armedReport } from "../game/armed-runners.js";
import { readDamagePredictionResult } from "../game/damage-prediction.js";
import { readTileCoord } from "./ai-step/internals.js";

// Attribution runner : les buffers sont SÉPARÉS PAR ORIGINE (OriginBuffers =
// Map originRunnerId → bucket, null = IA live ; CAP par bucket, éviction
// dropNew = comportement historique). Chaque event porte aussi
// `originRunnerId`. Dumps : `runnerId` → bucket direct ; sans → concat
// toutes origines (ordre seq). Clear scopable par `runnerId` ; le dispose
// d'un runner purge ses buckets automatiquement (cf. game/trace-origin.ts).

// Cap PAR BUCKET (par origine) de chaque famille de buffers ci-dessous.
const CAP = 4000;

// ================= CIBLES PAR ADRESSE — build `t6dpr4k06g` (les 13 y sont, #10011 + #10011-r1) =====
//
// ⚠ ON STOCKE LA **VA COMPLÈTE**, la RVA se calcule EN CODE. Écrire la RVA directement obligeait à
// soustraire 0x180000000 à la main — et cette soustraction a DÉJÀ été ratée : `RVA_VALUE_MOD_MODIFY`
// valait `0x1fadfc0` pour une VA `@180fadfc0` dont la RVA est `0xfadfc0`. La constante pointait donc
// en plein corps de `FPSCounterData$$set_Average`, une classe sans aucun rapport ; latente seulement
// parce que c'était un fallback derrière un `findMethod` qui réussit. La VA, elle, se grepe telle
// quelle dans `data/symbols/<build>/ghidra/functions.tsv`.
//
// MIGRATION : `python scripts/python/probe_257_scorer_rva_migration.py` fait l'aller-retour
// adresse→symbole→adresse et TRIE. Mais il ne suffit PAS — mesuré le 2026-07-29 :
//   * un POINT INTERNE ne se transpose pas : l'offset ne survit que si le corps n'a pas bougé.
//     `RVA_OVERRIDE_RETADDR` était à **243 octets** de ce que l'arithmétique prédisait ;
//   * un mécanisme peut CHANGER DE FORME, pas seulement d'adresse : l'index d'interface de `b__1`
//     est passé de `0xb4` à `0xb5`, et `b__0` est passé à un appel de vtable ;
//   * pour situer un SITE D'APPEL, interroger les xrefs du **CALLEE**, jamais des données qu'il
//     consomme — partir du DAT rendait 7 sites ambigus ET masquait un second appel.
// Détail complet, cible par cible : tâche #257.
// #475 : ces cibles passent TOUTES par le FOYER `il2cpp/build-pin.ts` (`pinnedAddress`), qui
// refuse d'attacher dès que le build chargé n'est plus celui sur lequel la VA a été mesurée.
// Le commentaire ci-dessus disait déjà « au prochain build, ces RVA pointent du code aléatoire » —
// il ne l'EMPÊCHAIT pas. Maintenant si. Chaque pin porte son symbole ghidra VERBATIM, que le
// cliquet `probe_475_pinned_addresses.py` confronte OFFLINE à la table versionnée du build
// DÉCLARÉ : c'est ce qui attrape une transcription fausse À L'INTÉRIEUR du bon build — exactement
// la faute `RVA_VALUE_MOD_MODIFY` décrite plus bas. Le hash est réécrit dans CHAQUE pin, sans
// constante partagée : un pin doit se lire seul (deux pins peuvent légitimement déclarer des
// builds différents — c'est le cas dans `modifier-observe.ts`).

// ComposedUtility.<EvaluateMovementInSteps>d__8.MoveNext. Le composite Tile(7) est un ComposedUtility
// qui SOMME ses enfants (liste List<IUtility> @ this+0x18, this = d__8+0x20). On énumère les noms de
// classe des enfants (une fois par instance `this`) pour IDENTIFIER de façon déterministe la feuille
// -25 (plutôt que hooker feuille par feuille).
const PIN_COMPOSED_UTILITY: PinnedAddress = {
    va: 0x1812130f0, build: "t6dpr4k06g",
    symbol: "IdunBattle.AI.Utilities.ComposedUtility.u003CEvaluateMovementInStepsu003Ed__8$$MoveNext",
    what: "itérateur du composite Tile(7) — énumère ses enfants",
    how: "search_symbols_by_name sur ComposedUtility.<EvaluateMovementInSteps>d__8.MoveNext,"
        + " ou grep du symbole dans data/symbols/<build>/ghidra/functions.tsv (occurrence UNIQUE)",
};

// DamageCalculations.GetMultiplierFromDamageBonus @181005210 (RVA 0x1005210) — convertit un bonus %
// (Nullable<int> @ param_3+0x20) en multiplicateur (>0: 1+b/100 ; <0: 1-|b|/100). Signature :
// (param_1 out Nullable<Fix64>*, param_2 ctx, param_3). RETOURNE param_1 = le multiplicateur Fix64 (@0).
// Hooké pour CAPTURER chaque bonus appliqué pendant la prédiction (le +50 sur 82, le -30 sur 78) + backtrace :
// le RETURN-ADDRESS = le CALL SITE source, qui distingue ATTAQUANT (CalculateAttackerModifiersForPrediction
// @181000590 : 4 sites — statmods @181001947 ; positionnels elevation/RangedInMelee/Trench @181001ef9/
// 181001ff2/1810020df) vs DÉFENSEUR (CalculateDefenderModifiersForPrediction @181002c30, site @181003d51).
// ⚠ ON NE HOOKE QUE la variante SINGLE. Le symbole porte DEUX occurrences, et l'ORDRE DES ADRESSES NE
// LES DÉPARTAGE PAS — il faut lire les corps. Re-mesuré sur `t6dpr4k06g` (les deux occurrences sont
// `18110c980` et `18110ca70`), avec les MÊMES trois critères qu'au 2026-07-29 sur `rnca9r7q6c` :
//   la SINGLE prend `damageBonus` (SINGULIER), lit le Nullable via `in_R8` (= param_3) et appelle
//              `IdunBattle.Core.Services.BaseCalculations$$GetFloatMultiplierFromPercentage` → C'EST CELLE-CI ;
//   la LIST   prend `damageBonuses` (PLURIEL), énumère une `List<>` et RAPPELLE la single en interne.
// Les trois critères concordent tous les trois sur la MÊME occurrence — aucun n'a eu à trancher seul.
// Hooker la LIST lisait un `args[2]` parasite (bonus=1) ; et comme elle délègue, la single capte DÉJÀ
// chaque bonus.
// ⚠ ET IL Y EN A UNE TROISIÈME, SUR UNE AUTRE CLASSE : `IdunBattle.Core.Services.RepairCalculations`
// porte le MÊME nom court. Un `search_symbols_by_name GetMultiplierFromDamageBonus` rend donc TROIS
// lignes, pas deux — c'est le symbole PLEINEMENT QUALIFIÉ (`DamageCalculations$$…`) qui en ramène deux.
const PIN_GET_MULT_DMG_BONUS: PinnedAddress[] = [{
    va: 0x18110c980, build: "t6dpr4k06g",
    symbol: "IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus",
    what: "convertit UNE contribution en multiplicateur — variante SINGLE (pas la LIST)",
    how: "search_symbols_by_name GetMultiplierFromDamageBonus rend TROIS lignes : filtrer sur la"
        + " classe DamageCalculations (la 3e est RepairCalculations), puis départager les DEUX"
        + " surcharges restantes par leur SIGNATURE au décompilé (singulier vs pluriel) — JAMAIS"
        + " par l'ordre des adresses dans la table",
}];

// #49 — RÉSOLVEUR DE L'OVERRIDE DE BASE (profileMethod). Deux délégués de GetAttackHitPrediction portent
// l'override base :
//   b__0 @1812edc90 : appelle une méthode VIRTUELLE de l'instance (param_1+0x10).
//        ⚠ CE DÉLÉGUÉ A CHANGÉ DE FORME sur `rnca9r7q6c` : il fait désormais un appel de VTABLE
//        `(*(code **)(*plVar1 + 0x4d8))(plVar1, &arg, *(plVar1 + 0x4e0))` — slot @+0x4d8, MethodInfo
//        @+0x4e0 — là où il passait par l'invocateur d'interface. Re-RE avant d'exploiter b__0.
//   b__1 @1812eddd0 : appelle l'interface `DAT_1833419e0` **idx 0xb5** sur (param_1+0x10)+0x20.
// Ces slots sont résolus au RUNTIME → non mappables offline. Ce résolveur lit, pendant une prédiction
// live, la VA CONCRÈTE que chaque délégué invoque → on la décompile ensuite. Ciblage pur, aucune
// formule devinée.
// ⚠ LES SIX PINS SONT MIGRÉS SUR `t6dpr4k06g` (#10011-r1) — le bloc n'est donc plus refusé.
// `installBaseOverrideResolver` refuse toujours EN BLOC, mais c'est désormais une garde, plus un
// constat. Aucun des quatre derniers ne s'est re-dérivé par un grep de symbole, et c'est le point :
//   * les deux `DAT_*` viennent des corps décompilés qui les LISENT (b__1 pour l'un,
//     `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` pour l'autre) ;
//   * le placeholder `FUN_*` vient de la XREF ENTRANTE — c'est le CALLEE du call idx-0xd de
//     `PredictAttackRaw` — et de son CORPS (il fait le walk d'itable
//     `klass+0xb0` / count `klass+0x12e` / `vid = klass+0x138 + (off+idx)*0x10`, repli
//     `FUN_1801e72b0`). Son adresse n'a PAS bougé de `rnca9r7q6c` à `t6dpr4k06g` : c'est une
//     OBSERVATION, jamais la preuve — le nom d'un `FUN_*` étant son ancienne adresse, il aurait
//     pu désigner n'importe quoi ;
//   * le point INTERNE est DÉSASSEMBLÉ (cf. plus bas), jamais transposé.
// ⚠ ET L'ADRESSE NE SUFFIT PAS : sur `rnca9r7q6c` la FORME du corps de `b__0` avait changé, et
// `ATTACK_IFACE_IDX` était passé de 0xb4 à 0xb5. Les DEUX ont été RELUS au décompilé sur
// `t6dpr4k06g` et sont INCHANGÉS : `b__0` fait toujours
// `(*(code **)(*plVar1 + 0x4d8))(plVar1, &arg, *(plVar1 + 0x4e0))`, et `b__1` porte `0xb5` aux
// DEUX endroits (scan d'itable et repli). Les relire reste obligatoire au prochain build.
const PIN_PROFILE_B0: PinnedAddress = {
    va: 0x1812ee740, build: "t6dpr4k06g",
    symbol: "IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility"
        + ".u003Cu003Ec__DisplayClass9_0$$u003CGetAttackHitPredictionu003Eb__0",
    what: "délégué b__0 de GetAttackHitPrediction — porte l'override de base (vtable+0x4d8)",
    how: "grep du symbole dans data/symbols/<build>/ghidra/functions.tsv (occurrence UNIQUE)",
};
const PIN_PROFILE_B1: PinnedAddress = {
    va: 0x1812ee880, build: "t6dpr4k06g",
    symbol: "IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility"
        + ".u003Cu003Ec__DisplayClass9_0$$u003CGetAttackHitPredictionu003Eb__1",
    what: "délégué b__1 de GetAttackHitPrediction — override de base via interface idx 0xb5",
    how: "grep du symbole dans data/symbols/<build>/ghidra/functions.tsv (occurrence UNIQUE)",
};
// ⚠ L'INDEX AVAIT BOUGÉ AVEC LE BUILD : 0xb4 → 0xb5. Il est RELU à chaque migration, jamais reconduit.
// Sur `t6dpr4k06g` il vaut TOUJOURS 0xb5, relevé DEUX fois dans `b__1` — dans le scan de l'itable
// `(off + 0xb5) * 0x10 + 0x138 + klass`, et dans le repli `FUN_1801e72b0(svc, DAT, 0xb5)`.
// Transposer la seule adresse en gardant un index périmé résoudrait LE MAUVAIS SLOT, en rendant un
// pointeur de fonction parfaitement valide — donc sans la moindre erreur visible.
// DONNÉE, pas code : `kind: "data"` le DIT, et c'est ce qui dispense le cliquet de chercher un
// symbole de fonction (il vérifie au lieu que la VA tombe hors de la zone des fonctions).
// La VA se LIT dans le corps de `b__1` (l'opérande comparée aux entrées d'itable) — un `DAT_*` est
// absent de `functions.tsv` par construction, donc aucun grep ne peut le rendre.
const PIN_ATTACK_IFACE: PinnedAddress = {
    va: 0x1833419e0, build: "t6dpr4k06g", kind: "data", symbol: "DAT_1833419e0",
    what: "Il2CppClass* de l'interface ability (scan de l'itable de b__1)",
};
const ATTACK_IFACE_IDX = 0xb5;
// Le VRAI override de base : `PredictAttackRaw` fait `FUN_180031990(out, idx=0xd, DAT_18334b2f8, recv)`
// → Nullable<Fix64> ; si HasValue, remplace la base. On résout le receiver (R9=args[3]) sur CE site
// (filtre returnAddress) → classe concrète + VA de la méthode idx 0xd → à décompiler pour LIRE la formule.
// L'ordre des paramètres est RELU sur le corps de l'invocateur : `(param_1 out, param_2 idx (ushort),
// param_3 iface, param_4 receiver, ...)` — c'est `param_4` dont il déréférence l'`Il2CppClass*`.
const PIN_IFACE_DMG: PinnedAddress = {
    va: 0x18334b2f8, build: "t6dpr4k06g", kind: "data", symbol: "DAT_18334b2f8",
    what: "Il2CppClass* de l'interface portant l'override de base (idx 0xd)",
};
const PIN_FUN_INVOKE: PinnedAddress = {
    va: 0x180031990, build: "t6dpr4k06g", symbol: "FUN_180031990",
    // `list_xrefs` rend DEUX appels DIRECTS (les deux dans `PredictAttackRaw`, idx 0xd et 0xe) plus
    // UNE référence DATA : le filtre `returnAddress` reste donc obligatoire — une invocation
    // indirecte par cette table n'apparaîtrait dans aucun appel direct.
    what: "invocateur d'interface générique — hook filtré par returnAddress",
    how: "placeholder FUN_* : aucun MethodInfo, donc NON résoluble par symbole. Partir de la XREF"
        + " ENTRANTE (le call idx-0xd de PredictAttackRaw) puis VÉRIFIER LE CORPS : il doit faire"
        + " le walk d'itable klass+0xb0 / count klass+0x12e / vid = klass+0x138 + (off+idx)*0x10."
        + " Son adresse est restée la même de rnca9r7q6c a t6dpr4k06g — c'est une observation,"
        + " jamais la preuve.",
};
// return-addr du call idx-0xd (isole CE site, évite le hot broad-hook).
// ⚠ DÉSASSEMBLÉ, PAS TRANSPOSÉ. `list_xrefs` sur le CALLEE donne DEUX appels dans `PredictAttackRaw`
// (1811168b6 et 181116e18 sur `t6dpr4k06g`). Le premier porte `0xd`, le call fait 5 octets
// (`e8 d5 b0 f1 fe`, vérifié à l'octet), donc le retour est à `1811168bb`. L'ancien offset (+0x18EE)
// avait déjà donné 243 octets à côté, en plein milieu d'une instruction : on ne transpose pas.
// ⚠ LE RÉSIDU QUI ÉTAIT NOMMÉ ICI EST FERMÉ : l'index du SECOND appel est ÉTABLI, il vaut **0xe**,
// pas 0xd (`FUN_180031990(&local_7c8, 0xe, DAT_18334b2f8)`). Le filtre `returnAddress` sélectionne
// donc bien un site UNIQUE pour l'override de base — les deux sites ne sont pas équivalents.
// ⚠ L'offset `+0x17fb` est le MÊME que sur `rnca9r7q6c` — coïncidence de corps inchangé dans cette
// zone, PAS une règle : il a été re-dérivé par désassemblage, pas reconduit.
const PIN_OVERRIDE_RETADDR: PinnedAddress = {
    va: 0x1811168bb, build: "t6dpr4k06g",
    symbol: "IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x17fb",
    what: "return-address du call idx-0xd — isole CE site (le second call porte l'idx 0xe)",
    how: "DÉSASSEMBLER, ne pas transposer : list_xrefs sur le CALLEE, LIRE l'idx de chaque site"
        + " (0xd vs 0xe), le call fait 5 octets. Un offset transposé était déjà tombé 243 octets"
        + " à côté.",
};
const baseOverrideResolved = new Set<string>();
let overrideIdxdResolved = false;      // resolve-once (reset au clear global)

// --- Corps PLEINEMENT PARTAGÉS de `ComparablePlaybook<T>` : RÉSOLUTION RUNTIME ------------
//
// `CalculateActionUtility` (utilité TOTALE par candidat — le discriminateur du pick, le dégât
// seul ne suffit pas) et `CalculateUtilityFromTilePrediction` (terme de tuile COMPLET, composite
// Tile(7) = somme des 29 feuilles, appelée DANS la précédente) portaient une adresse en dur.
// Elles n'en portent plus : elles se résolvent au runtime, comme l'exige le CLAUDE.md.
//
// CE QUI LE REND POSSIBLE, et c'est MESURÉ (#259-b, `probe_262_gshared_runtime.py`) : le
// `MethodInfo` d'une instance INFLATÉE porte bien le corps pleinement partagé. `findMethod` sur
// la classe CONCRÈTE échoue (elle ne déclare pas la méthode, et `findMethod` ne remonte PAS les
// parents) — mais sur son PARENT, l'instance inflatée `ComparablePlaybook<TAbility>`, elle rend
// exactement `ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`,
// à l'offset 0, et LA MÊME adresse pour les quatre classes concrètes essayées.
//
// À ne pas confondre avec la voie RÉFUTÉE (#259, §3) : le `methodPointer` d'une DÉFINITION
// générique est un thunk d'invocation. C'est l'INSTANCE inflatée qui porte le corps.
//
// Plusieurs graines, et c'est délibéré : si l'une disparaît d'un build, les autres couvrent.
// Aucune ne sert de « meilleure » — la première qui résout gagne, elles rendent la même adresse.
const COMPARABLE_PLAYBOOK_SEEDS = [
    "MurderousSwingPlaybook", "BlightGrenadesPlaybook",
    "EntropyCannonsPlaybook", "LightOfSanguiniusPlaybook",
];

function resolveSharedPlaybookBody(method: string): NativePointer | null {
    for (const cls of COMPARABLE_PLAYBOOK_SEEDS) {
        const k = findClassAnywhere("IdunBattle.AI.Playbook", cls);
        if (!k) continue;
        const parent = class_get_parent(k) as NativePointer;   // instance INFLATÉE
        if (parent.isNull()) continue;
        const m = findMethod(parent, method);
        if (m && !m.ptr.isNull()) {
            log("[scorer-trace] " + method + " résolu via " + cls
                + " -> " + m.ptr + " (rva 0x" + m.ptr.sub(il2cppBase).toString(16) + ")");
            return m.ptr;
        }
    }
    log("[scorer-trace] " + method + " NON RÉSOLU sur les "
        + COMPARABLE_PLAYBOOK_SEEDS.length + " graines — hook non posé."
        + " Ce n'est PAS un cas pour ressortir une adresse en dur : c'est une vraie"
        + " limitation à investiguer (cf. docs/rl/case-259-couverture-gshared.md).");
    return null;
}

// ElevationUtility.<EvaluateMovementInSteps>d__8.MoveNext (itérateur, non résolu par findMethod)
// — adresse build-spécifique (ghidra @1811019a0 - 0x180000000). Confirme la feuille Elevation :
// valeur d'élévation NATIVE de la tuile candidate (util+0x6c), max (util+0x60) / min (util+0x64) du
// DOMAINE PERTINENT, et la sortie de feuille yieldée (d__8+0x18, Fix64). d__8+0x20 = l'ElevationUtility ;
// d__8+0x28 = la position candidate (MainTile via +0x18). À REFAIRE au changement de hash.
const PIN_ELEVATION_LEAF: PinnedAddress = {
    va: 0x181213610, build: "t6dpr4k06g",
    symbol: "IdunBattle.AI.Utilities.ElevationUtility.u003CEvaluateMovementInStepsu003Ed__8$$MoveNext",
    what: "feuille Elevation (itérateur MoveNext) — valeur d'élévation native + sortie de feuille",
    how: "grep du symbole dans data/symbols/<build>/ghidra/functions.tsv — occurrence UNIQUE,"
        + " donc re-dérivable sans décompiler. C'est l'un des DEUX canaux que `X_nat = Tile7 -"
        + " Elevation - TileEffects` retranche : quand il est muet, X_nat vaut None PARTOUT.",
};

// (CalculateUtilityFromTilePrediction se résout par `resolveSharedPlaybookBody` — cf. plus haut.
//  Retour Fix64 dans RAX ; appelée DANS CalculateActionUtility, donc `curCaster` est déjà posé
//  quand elle rend → sépare le damage-util du tile-term.)

interface UtilEvent {
    seq: number;
    originRunnerId: number | null;   // runner du RPC déclencheur (null = IA live)
    casterCol: number;
    casterRow: number;
    targets: number[];   // cibles des ProbableDamageEvents produits dans CET appel
    utility: number;     // Fix64 -> nombre
    hasValue: number;
    stack?: string[];    // backtrace (offsets rel. il2cppBase) — 1ers events seulement
}
const utilTrace: {
    buf: OriginBuffers<UtilEvent>; targets: number[]; stacksLeft: number;
} = { buf: new OriginBuffers<UtilEvent>(CAP, "dropNew"),
      targets: [], stacksLeft: 0 };

interface ElevEvent {
    seq: number;
    originRunnerId: number | null;
    col: number;
    row: number;
    elev: number;   // valeur composant Elevation NATIVE de la tuile candidate (util+0x6c)
    max: number;    // max du domaine pertinent (util+0x60)
    min: number;    // min du domaine pertinent (util+0x64)
    leaf: number;   // sortie de feuille yieldée (d__8+0x18, Fix64 -> nombre)
    stack?: string[];  // backtrace (1ers events) -> révèle l'AGRÉGATEUR qui somme les feuilles
}
const elevTrace: { buf: OriginBuffers<ElevEvent>; stacksLeft: number } =
    { buf: new OriginBuffers<ElevEvent>(CAP, "dropNew"), stacksLeft: 0 };

interface TileTermEvent {
    seq: number;
    originRunnerId: number | null;
    casterCol: number;
    casterRow: number;
    tileTerm: number;   // composite Tile(7) COMPLET (retour Fix64 de CalculateUtilityFromTilePrediction)
}
const tileTermTrace: { buf: OriginBuffers<TileTermEvent> } =
    { buf: new OriginBuffers<TileTermEvent>(CAP, "dropNew") };

// Capture générique de la SORTIE d'une feuille de tuile situationnelle (itérateur *Utility.<d__N>.MoveNext).
// Layout itérateur : yielded Fix64 @ d__+0x18 ; utility @ d__+0x20 ou +0x28 ; position candidate à
// posOff (décodée en MainTile via +0x18). Sert à IDENTIFIER la feuille -25 active sur (5,3).
interface LeafEvent {
    seq: number;
    originRunnerId: number | null;
    leaf: string;   // label de la feuille (ex. "TileEffects", "Contaminated")
    col: number;
    row: number;
    value: number;  // sortie de feuille yieldée (significative seulement si ret==1)
    ret: number;    // retour MoveNext (1=valeur fraîche, 0=fin/gate) — voir quels enfants sont appelés
}
const leafTrace: { buf: OriginBuffers<LeafEvent> } =
    { buf: new OriginBuffers<LeafEvent>(CAP, "dropNew") };

// Énumération des enfants des composites vus (dédup par ptr `this`). key = ptr hex, val = [classNames].
const composedChildren: { seen: Map<string, string[]> } = { seen: new Map() };

interface BonusEvent {
    seq: number;
    originRunnerId: number | null;
    bonus: number;       // valeur du bonus % (param_3+0x20 Nullable<int>) — +50, -30, …
    mult: number;        // multiplicateur en SORTIE (retval = param_1, Fix64 @0) — cross-check : 0.70 <-> bonus -30
    hasValue: number;
    casterCol: number;   // tuile caster courante (via CalculateActionUtility) — corrèle le CS tile-dépendant
    casterRow: number;
    stack?: string[];    // backtrace -> return-address = CALL SITE source (att statmods/positional vs def)
}
const bonusTrace: { buf: OriginBuffers<BonusEvent>; stacksLeft: number } =
    { buf: new OriginBuffers<BonusEvent>(CAP, "dropNew"), stacksLeft: 0 };
// Capture GÉNÉRIQUE de la sortie yieldée d'une feuille de tuile (*Utility.<d__N>.MoveNext). Machinerie
// réutilisable : `scorerLeafTraceDump` donne la valeur + tuile candidate par feuille hookée. Set par
// DÉFAUT minimal (TileEffects = la feuille -25 identifiée + CapturePoint = contrôle connu-firing) ;
// pour investiguer d'autres feuilles, énumérer d'abord les enfants d'un composite via `scorerComposedDump`
// puis AJOUTER ici les VA voulues (VA COMPLÈTE ghidra → RVA = va − base, en code, cf. la transcription
// 0x1810fXXXX → 0x10fXXXX). ⚠ NE PAS dépasser ~10 hooks à la fois (35 = cctor cascade → détache la
// session) NI hooker des feuilles CHAUDES (distances MinDist/MaxDist/TileDistance : PAS enfants du
// composite Tile de toute façon). La position candidate est décodée par essai d'offsets (0x28/0x20).
// (`IL2CPP_VA_BASE` et `rva()` sont déclarés en tête, avec le bloc des cibles par adresse.)
const LEAF_HOOKS: Array<[PinnedAddress, string]> = [
    [{ va: 0x18120d810, build: "t6dpr4k06g",
       symbol: "IdunBattle.AI.Utilities.TileEffectsUtility"
           + ".u003CEvaluateMovementInStepsu003Ed__1$$MoveNext",
       what: "feuille -25 (Thorns_DefenseReduction) — SECOND canal retranché par X_nat",
       how: "grep du symbole dans data/symbols/<build>/ghidra/functions.tsv (occurrence UNIQUE)" },
     "TileEffects"],
    [{ va: 0x181211a80, build: "t6dpr4k06g",
       symbol: "IdunBattle.AI.Utilities.CapturePointTileUtility"
           + ".u003CEvaluateMovementInStepsu003Ed__3$$MoveNext",
       what: "contrôle : feuille connue-firing (sanity du mécanisme de hook)",
       how: "grep du symbole dans data/symbols/<build>/ghidra/functions.tsv (occurrence UNIQUE)" },
     "CapturePointTile"],
];
const LEAF_POS_OFFSETS = [0x28, 0x20];

interface DmgEvent {
    seq: number;
    originRunnerId: number | null;
    targetId: number;
    targetType: number;
    curHealth: number;
    healthMin: number;
    healthMax: number;
    // `ShieldDamage` = le MinMaxDamage que `IdunBattle.AI.Utilities.DamageUtility$$GetShieldDamage`
    // moyenne — consommé par `DamageUtility.MoveNext` (D = hAvg + sAvg). `LimitedByMinHp` : si posé,
    // `DamageUtility$$GetHealthDamage` retourne `CurrentHealth` entier. Offsets : #276, cf.
    // `game/damage-prediction.ts` (ceux d'ici étaient périmés depuis la migration `rnca9r7q6c`).
    shieldMin: number;
    shieldMax: number;
    limitedByMinHp: number;
    hits: number;
    /** Violations de forme du décodage (non nul = le décodeur ne décode plus ce struct). */
    shapeErrors: string[] | null;
    // Tuile caster du candidat (via MakeDamagePredictions param_3=position) — le nerf de
    // CrushingStrike (+50% mêlée si non-bougé) dépend de si cette tuile == pos courante du caster.
    casterCol: number;
    casterRow: number;
}

// Position caster du candidat courant, posée par le hook MakeDamagePredictions onEnter et lue par
// le ctor ProbableDamageEvent qui suit immédiatement (1 MakeDamagePredictions -> ses events).
let curCaster: { col: number; row: number } | null = null;

// #49 — tuile de la PRÉDICTION courante, posée par le hook PredictAttackRaw onEnter (scan du context
// pour la UnitPosition) et lue par les hooks NESTÉS (statMods/attMod firent DANS PredictAttackRaw). Robuste
// (sur le chemin de prédiction par construction) là où curCaster (via CalculateActionUtility) est découplé.
let curPredTile: { col: number; row: number } | null = null;

// LA PORTE N'EST PLUS UN BOOLEEN DE MODULE (#483). `trace.on` est un ACCESSEUR qui
// consulte l'armement PAR RUNNER (`capturing`) contre l'origine COURANTE
// (`getTraceOrigin`). Les ~20 gardes `if (!trace.on) return;` de ce fichier n'ont pas
// bougé d'un caractère : c'est ce que le point de lecture DÉCIDE qui a changé.
// Pourquoi ça compte : les probes appellent `scorerDamageTraceOff` dans un `finally`,
// donc en 4-en-parallèle le premier qui finissait désarmait la capture des autres,
// qui dumpaient un seau TRONQUÉ sans erreur. Cf. game/armed-runners.ts.
const trace: { readonly on: boolean; seq: number; buf: OriginBuffers<DmgEvent> } = {
    get on(): boolean { return capturing("scorerDamage"); },
    seq: 0, buf: new OriginBuffers<DmgEvent>(CAP, "dropNew"),
};

// DamagePrediction.CalculateBaseDamageWithAllModifiers @18102d3f0 (méthode NOMMÉE, findMethod —
// survit au hash) : (this, int baseDamage, IEntity attacker, IEntity defender, DamageProfile,
// Nullable<DamageModifiers> att, Nullable<DamageModifiers> def, bool isCrit, bool isMelee) → Fix64.
// Capture (baseDamage, isCrit, isMelee, retour Fix64, call-site via returnAddress) par appel pendant
// aiStepDryRun → tranche le chemin santé par-coup des SPÉCIALES (÷hits ? crit du bout max ?).
interface AllModsEvent {
    seq: number;
    originRunnerId: number | null;
    input: number;      // baseDamage int (args[1])
    isCrit: number;
    isMelee: number;
    out: number;        // retour Fix64 -> nombre
    site: string;       // returnAddress rel. il2cppBase (hex) — distingue les call sites min/max
    casterCol: number;
    casterRow: number;
}
const allModsTrace: { buf: OriginBuffers<AllModsEvent> } =
    { buf: new OriginBuffers<AllModsEvent>(CAP, "dropNew") };
let allModsInstalled = false;

// #49 — capture le BASE-OVERRIDE : return[0] (Nullable) de CalculateAttackerModifiersForPrediction @181000590.
// PredictAttackRaw lit ce champ `HasValue → op_Explicit(Value)` pour REMPLACER la base 4309 (pré-spread).
// On lit plusieurs interprétations (Nullable<int> value@0/hasValue@4 ; Nullable<Fix64> value@0/hasValue@8)
// pour lever l'ambiguïté gshared, + tuile caster. Méthode NOMMÉE → findMethod (survit au hash).
interface AttModEvent {
    seq: number;
    originRunnerId: number | null;
    i0: number;     // int32 @0 (candidat Nullable<int>.value)
    hv4: number;    // byte @4 (candidat Nullable<int>.hasValue)
    f0: number;     // Fix64 @0 -> nombre (candidat Nullable<Fix64>.value)
    hv8: number;    // byte @8 (candidat Nullable<Fix64>.hasValue)
    add: number;    // #49 : retval+0x10 = DamageModifiers.additive (Fix64) — le NET ±mods appliqué à la base
    casterCol: number;
    casterRow: number;
}
const attModTrace: { buf: OriginBuffers<AttModEvent> } =
    { buf: new OriginBuffers<AttModEvent>(CAP, "dropNew") };
let attModInstalled = false;
function installAttModHook(): boolean {
    if (attModInstalled) return true;
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamageCalculations");
    if (!klass) { log("[scorer-trace] DamageCalculations class not found (attMod)"); return false; }
    const mi = findMethod(klass, "CalculateAttackerModifiersForPrediction");
    if (!mi || mi.ptr.isNull()) { log("[scorer-trace] CalculateAttackerModifiersForPrediction not resolved"); return false; }
    Interceptor.attach(mi.ptr, {
        onLeave(retval) {
            if (!trace.on) return;
            try {
                if (retval.isNull()) return;
                const i0 = retval.readS32();
                const hv4 = retval.add(4).readU8();
                let raw = BigInt(retval.readS64().toString());
                if (raw >= (1n << 63n)) raw -= (1n << 64n);
                const f0 = Number(raw) / 4294967296;
                const hv8 = retval.add(8).readU8();
                let addRaw = BigInt(retval.add(0x10).readS64().toString());   // DamageModifiers.additive @+0x10
                if (addRaw >= (1n << 63n)) addRaw -= (1n << 64n);
                const add = Number(addRaw) / 4294967296;
                attModTrace.buf.push({
                    seq: ++trace.seq, originRunnerId: getTraceOrigin(),
                    i0, hv4, f0, hv8, add,
                    casterCol: curPredTile ? curPredTile.col : (curCaster ? curCaster.col : -1),
                    casterRow: curPredTile ? curPredTile.row : (curCaster ? curCaster.row : -1),
                });
            } catch { /* transient */ }
        },
    });
    attModInstalled = true;
    log("[scorer-trace] hooked CalculateAttackerModifiersForPrediction @ " + mi.ptr);
    return true;
}

// #49 — LE hook décisif : CalculateModifiersFromStatModifications @181004380 (méthode NOMMÉE → findMethod,
// survit au hash). En hookant la FONCTION (et non le call-site), `args[2]` = le param `negate` est
// NON-AMBIGU (aucun shuffle d'args côté appelant gshared) → tranche add(0) vs subtract(1). On lit aussi le
// StatComponent d'entrée (args[1]) : Initial @+0x48 (=3011 identifie l'Attack de u92) + candidats mod, et
// en sortie le nb de modifiers produits (List _size @+0x18). Corrèle par tuile caster (curCaster).
interface StatModsEvent {
    seq: number;
    originRunnerId: number | null;
    negate: number;     // args[2] byte — 0=ADDITION, 1=SUBTRACTION (le signe cherché)
    initial: number;    // StatComponent+0x48 (Initial) — 3011 => stat Attack u92
    mod10: number;      // StatComponent+0x10 lu inline (candidat ValueModification.total)
    mod10ptr: number;   // *(StatComponent+0x10)+0 (candidat si +0x10 est un pointeur)
    listCount: number;  // retour = List<DamageModifier> _size @+0x18 (0 = garde Current==Initial)
    casterCol: number;
    casterRow: number;
}
const statModsTrace: { buf: OriginBuffers<StatModsEvent> } =
    { buf: new OriginBuffers<StatModsEvent>(CAP, "dropNew") };
let statModsInstalled = false;
function installStatModsHook(): boolean {
    if (statModsInstalled) return true;
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamageCalculations");
    if (!klass) { log("[scorer-trace] DamageCalculations class not found (statMods)"); return false; }
    const mi = findMethod(klass, "CalculateModifiersFromStatModifications");
    if (!mi || mi.ptr.isNull()) { log("[scorer-trace] CalculateModifiersFromStatModifications not resolved"); return false; }
    Interceptor.attach(mi.ptr, {
        onEnter(args) {
            if (!trace.on) return;
            const self = this as { _on?: boolean; _neg?: number; _init?: number; _m10?: number; _m10p?: number };
            self._on = true;
            try {
                self._neg = args[2].toInt32() & 0xff;
                const stat = args[1];
                if (stat && !stat.isNull()) {
                    self._init = stat.add(0x48).readS32();
                    self._m10 = stat.add(0x10).readS32();
                    try { const p = stat.add(0x10).readPointer(); self._m10p = (!p.isNull()) ? p.readS32() : -1; }
                    catch { self._m10p = -1; }
                }
            } catch { self._on = false; }
        },
        onLeave(retval) {
            const self = this as { _on?: boolean; _neg?: number; _init?: number; _m10?: number; _m10p?: number };
            if (!self._on || !trace.on) return;
            try {
                let listCount = -1;
                if (retval && !retval.isNull()) { try { listCount = retval.add(0x18).readS32(); } catch { /* */ } }
                statModsTrace.buf.push({
                    seq: ++trace.seq, originRunnerId: getTraceOrigin(),
                    negate: self._neg ?? -1, initial: self._init ?? -1,
                    mod10: self._m10 ?? -1, mod10ptr: self._m10p ?? -1, listCount,
                    casterCol: curPredTile ? curPredTile.col : (curCaster ? curCaster.col : -1),
                    casterRow: curPredTile ? curPredTile.row : (curCaster ? curCaster.row : -1),
                });
            } catch { /* transient */ }
        },
    });
    statModsInstalled = true;
    log("[scorer-trace] hooked CalculateModifiersFromStatModifications @ " + mi.ptr);
    return true;
}

// #49 — LE hook du GATE : ValueModification.Modify @180fadfc0 (source, amount) écrit UNE contribution
// stat-mod. La base f58 varie (3011/4309) => le +1298 est TOGGLÉ sur le stat Attack par-candidat. Ce
// hook capture chaque Modify de gros montant (|amount|>=500 => filtre le +1298, ignore le bruit) AVEC
// BACKTRACE (1ers events) → la pile révèle la FONCTION qui applique/retire le +1298 pendant la prédiction
// = le GATE cherché. + source entity (qui applique). findMethod (ValueModification concret), RVA fallback.
// ⚠ CETTE CONSTANTE ÉTAIT FAUSSE DEPUIS L'ORIGINE : elle valait `0x1fadfc0` alors que la VA citée par
// son propre commentaire (`@180fadfc0`) a pour RVA `0xfadfc0`. Elle pointait donc en plein corps de
// `CodeStage.AdvancedFPSCounter...FPSCounterData$$set_Average` — latente uniquement parce que c'est un
// FALLBACK derrière un `findMethod` qui réussit. C'est la faute exacte que la forme `rva(<VA>)` supprime.
const PIN_VALUE_MOD_MODIFY: PinnedAddress = {
    va: 0x1810b90b0, build: "t6dpr4k06g",
    symbol: "IdunBattle.Entities.Components.ValueModification$$Modify",
    what: "repli quand findMethod échoue — capture les Modify de gros montant",
    how: "grep du symbole dans data/symbols/<build>/ghidra/functions.tsv (occurrence UNIQUE)",
};
interface ModifyEvent {
    seq: number;
    originRunnerId: number | null;
    amount: number;     // args[2] (int) — la contribution écrite (~1298 pour le buff u92)
    srcId: number;      // args[1] source entity id @+0x10
    srcType: number;    // args[1] source entity type @+0x14
    stack?: string[];   // backtrace (1ers events) — return-addr = call-site = la fonction-GATE
}
const modifyTrace: { buf: OriginBuffers<ModifyEvent>; stacksLeft: number } =
    { buf: new OriginBuffers<ModifyEvent>(CAP, "dropNew"), stacksLeft: 0 };
let modifyInstalled = false;
function installModifyHook(): boolean {
    if (modifyInstalled) return true;
    let ptr: NativePointer | null = null;
    const klass = findClassAnywhere("IdunBattle.Entities.Components", "ValueModification");
    if (klass) { const mi = findMethod(klass, "Modify"); if (mi && !mi.ptr.isNull()) ptr = mi.ptr; }
    if (!ptr) {
        ptr = pinnedAddress(PIN_VALUE_MOD_MODIFY);
        if (!ptr) return false;   // le foyer a imprimé la cause — on n'attache PAS en aveugle
        log("[scorer-trace] ValueModification.Modify via adresse ÉPINGLÉE @ " + ptr);
    }
    Interceptor.attach(ptr, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const amount = args[2].toInt32();
                if (Math.abs(amount) < 500) return;   // ignore les petits mods (mouvement +1, etc.)
                const src = args[1];
                const srcId = (src && !src.isNull()) ? src.add(0x10).readS32() : -1;
                const srcType = (src && !src.isNull()) ? src.add(0x14).readS32() : -1;
                const ev: ModifyEvent = {
                    seq: ++trace.seq, originRunnerId: getTraceOrigin(),
                    amount, srcId, srcType,
                };
                if (modifyTrace.stacksLeft > 0) {
                    try {
                        ev.stack = Thread.backtrace(this.context, Backtracer.ACCURATE)
                            .slice(0, 14)
                            .map((a) => {
                                const off = a.sub(il2cppBase);
                                return (off.compare(0) > 0 && off.compare(il2cppBase) < 0)
                                    ? "il2cpp+0x" + off.toString(16) : a.toString();
                            });
                        modifyTrace.stacksLeft--;
                    } catch { /* */ }
                }
                modifyTrace.buf.push(ev);
            } catch { /* transient */ }
        },
    });
    modifyInstalled = true;
    log("[scorer-trace] hooked ValueModification.Modify @ " + ptr);
    return true;
}

// #49 — capture la BASE PRÉ-SPREAD fed to PredictAttackRaw : GetValueOrDefault(param_3 + 0x58). param_3 = R8
// = args[2] (context). Si args[2]+0x58 = 3011 aux tuiles réduites / 4309 aux pleines → le 3011 est DÉJÀ dans
// le base à l'entrée de PredictAttackRaw (posé en amont), PAS un modifier interne. On lit plusieurs offsets
// candidats (le layout Nullable peut décaler). PredictAttackRaw = gshared → findMethod peut échouer → RVA fallback.
const PIN_PREDICT_ATTACK_RAW: PinnedAddress = {
    va: 0x1811150c0, build: "t6dpr4k06g",
    symbol: "IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw",
    what: "repli quand findMethod échoue (gshared) — base pré-spread au contexte+0x58",
    how: "grep du symbole dans data/symbols/<build>/ghidra/functions.tsv (occurrence UNIQUE)",
};
interface PredBaseEvent {
    seq: number;
    originRunnerId: number | null;
    i58: number;    // int32 @+0x58
    f58: number;    // Fix64 @+0x58 -> nombre
    hv60: number;   // byte @+0x60
    i50: number;    // int32 @+0x50 (offset voisin, au cas où)
    f50: number;    // Fix64 @+0x50
    posCol: number; // tuile candidate décodée du context (scan) — LA corrélation base<->tuile (#49)
    posRow: number;
    posOff: number; // offset où la position a décodé (diagnostic)
    casterCol: number;
    casterRow: number;
}
const predBaseTrace: { buf: OriginBuffers<PredBaseEvent> } =
    { buf: new OriginBuffers<PredBaseEvent>(CAP, "dropNew") };
let predBaseInstalled = false;
function installPredictBaseHook(): boolean {
    if (predBaseInstalled) return true;
    let ptr: NativePointer | null = null;
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamagePrediction");
    if (klass) {
        const mi = findMethod(klass, "PredictAttackRaw");
        if (mi && !mi.ptr.isNull()) ptr = mi.ptr;
    }
    if (!ptr) {
        ptr = pinnedAddress(PIN_PREDICT_ATTACK_RAW);
        if (!ptr) return false;   // le foyer a imprimé la cause — on n'attache PAS en aveugle
        log("[scorer-trace] PredictAttackRaw via adresse ÉPINGLÉE @ " + ptr);
    }
    const f64 = (p: NativePointer): number => {
        try { let r = BigInt(p.readS64().toString()); if (r >= (1n << 63n)) r -= (1n << 64n); return Number(r) / 4294967296; }
        catch { return NaN; }
    };
    Interceptor.attach(ptr, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const ctx = args[2];   // param_3 (R8) = context ; base Nullable @+0x58
                if (ctx.isNull()) return;
                // Scan du context pour la UnitPosition candidate (robuste, sur le chemin de prédiction) →
                // pose curPredTile pour les hooks nestés (statMods/attMod). posOff = offset trouvé (diag).
                let posCol = -1, posRow = -1, posOff = -1;
                for (let off = 0; off <= 0x120; off += 8) {
                    try {
                        const c = decodePos(ctx.add(off));
                        if (c && c.col >= 0 && c.row >= 0) { posCol = c.col; posRow = c.row; posOff = off; break; }
                    } catch { /* offset suivant */ }
                }
                curPredTile = (posCol >= 0) ? { col: posCol, row: posRow } : null;
                predBaseTrace.buf.push({
                    seq: ++trace.seq, originRunnerId: getTraceOrigin(),
                    i58: ctx.add(0x58).readS32(), f58: f64(ctx.add(0x58)), hv60: ctx.add(0x60).readU8(),
                    i50: ctx.add(0x50).readS32(), f50: f64(ctx.add(0x50)),
                    posCol, posRow, posOff,
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                });
            } catch { /* transient */ }
        },
        // NB : on NE clear PAS curPredTile onLeave — le ctor ProbableDamageEvent (avec les hits=arme) fire
        // APRÈS PredictAttackRaw ; il doit lire la tuile de CETTE prédiction (écrasée par la suivante).
    });
    predBaseInstalled = true;
    log("[scorer-trace] hooked PredictAttackRaw (base fed-in) @ " + ptr);
    return true;
}
function installAllModsHook(): boolean {
    if (allModsInstalled) return true;
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamagePrediction");
    if (!klass) { log("[scorer-trace] DamagePrediction class not found"); return false; }
    const mi = findMethod(klass, "CalculateBaseDamageWithAllModifiers");
    if (!mi || mi.ptr.isNull()) { log("[scorer-trace] CalculateBaseDamageWithAllModifiers not resolved"); return false; }
    Interceptor.attach(mi.ptr, {
        onEnter(args) {
            if (!trace.on) return;
            const self = this as { _in?: number; _crit?: number; _melee?: number; _site?: string; _on?: boolean };
            self._on = true;
            self._in = args[1].toInt32();
            self._crit = args[7].toInt32() & 0xff;
            self._melee = args[8].toInt32() & 0xff;
            try {
                const off = this.returnAddress.sub(il2cppBase);
                self._site = "il2cpp+0x" + off.toString(16);
            } catch { self._site = "?"; }
        },
        onLeave(retval) {
            const self = this as { _in?: number; _crit?: number; _melee?: number; _site?: string; _on?: boolean };
            if (!self._on || !trace.on) return;
            try {
                let raw = BigInt(retval.toString());
                if (raw >= (1n << 63n)) raw -= (1n << 64n);
                allModsTrace.buf.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    input: self._in ?? -1, isCrit: self._crit ?? -1, isMelee: self._melee ?? -1,
                    out: Number(raw) / 4294967296,
                    site: self._site ?? "?",
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                });
            } catch { /* transient — skip */ }
        },
    });
    allModsInstalled = true;
    log("[scorer-trace] hooked CalculateBaseDamageWithAllModifiers @ " + mi.ptr);
    return true;
}

// DamagePrediction.CalculateDamagePredictionScenario @18102ed00 (méthode NOMMÉE, findMethod — survit
// au hash) : le NOYAU par-coup de la boucle multi-hit. Signature (Ghidra) :
//   (param_1=out struct, param_2=service, param_3, param_4=target, param_5=rawMM(MinMaxDamageFix64
//    min Fix64@0x10 / max Fix64@0x18), param_6, param_7=int previousHitsPrediction, param_8=int prob,
//    param_9=out byte). Retourne param_1 : healthMin S32@0xc, healthMax S32@0x10.
// But #49 : capturer `prevHits` (param_7 = args[6]) par coup — la réduction per-cible ~1047-1298 que
// l'analyse statique/nombres n'a pas pu nommer (perHitList dispatch générique). rawMin doit == per_coup
// (1799) et out la sortie santé du coup.
interface ScenarioEvent {
    seq: number;
    originRunnerId: number | null;
    targetId: number;   // param_4 = args[3] = target entity -> id @0x10 (attribution sans ambiguite)
    rawMin: number;     // param_5 +0x10 (Fix64 -> int)
    rawMax: number;     // param_5 +0x18
    prevHits: number;   // param_7 = args[6]
    prob: number;       // param_8 = args[7]
    outMin: number;     // retval +0xc
    outMax: number;     // retval +0x10
    casterCol: number;
    casterRow: number;
}
const scenarioTrace: { buf: OriginBuffers<ScenarioEvent> } =
    { buf: new OriginBuffers<ScenarioEvent>(CAP, "dropNew") };
let scenarioInstalled = false;
function installScenarioHook(): boolean {
    if (scenarioInstalled) return true;
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamagePrediction");
    if (!klass) { log("[scorer-trace] DamagePrediction class not found (scenario)"); return false; }
    const mi = findMethod(klass, "CalculateDamagePredictionScenario");
    if (!mi || mi.ptr.isNull()) { log("[scorer-trace] CalculateDamagePredictionScenario not resolved"); return false; }
    const f64 = (p: NativePointer): number => {
        try { return Number(p.readS64()) / 4294967296; } catch { return NaN; }
    };
    Interceptor.attach(mi.ptr, {
        onEnter(args) {
            if (!trace.on) return;
            const self = this as { _on?: boolean; _raw?: NativePointer; _prev?: number; _prob?: number; _tgt?: number };
            self._on = true;
            try {
                self._raw = args[4];
                self._prev = args[6].toInt32();
                self._prob = args[7].toInt32();
                const tgt = args[3];   // param_4 = target entity
                self._tgt = (tgt && !tgt.isNull()) ? tgt.add(0x10).readS32() : -1;
            } catch { self._on = false; }
        },
        onLeave(retval) {
            const self = this as { _on?: boolean; _raw?: NativePointer; _prev?: number; _prob?: number; _tgt?: number };
            if (!self._on || !trace.on) return;
            try {
                const raw = self._raw as NativePointer;
                scenarioTrace.buf.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    targetId: self._tgt ?? -1,
                    rawMin: raw && !raw.isNull() ? f64(raw.add(0x10)) : NaN,
                    rawMax: raw && !raw.isNull() ? f64(raw.add(0x18)) : NaN,
                    prevHits: self._prev ?? -1,
                    prob: self._prob ?? -1,
                    outMin: retval.add(0xc).readS32(),
                    outMax: retval.add(0x10).readS32(),
                    casterCol: curPredTile ? curPredTile.col : (curCaster ? curCaster.col : -1),
                    casterRow: curPredTile ? curPredTile.row : (curCaster ? curCaster.row : -1),
                });
            } catch { /* transient — skip */ }
        },
    });
    scenarioInstalled = true;
    log("[scorer-trace] hooked CalculateDamagePredictionScenario @ " + mi.ptr);
    return true;
}

let installed = false;
function installHook(): boolean {
    if (installed) return true;
    const klass = findClassAnywhere("IdunBattle.AI.Playbook", "ProbableDamageEvent");
    if (!klass) { log("[scorer-trace] ProbableDamageEvent class not found"); return false; }
    const ctor = findMethod(klass, ".ctor");
    if (!ctor || ctor.ptr.isNull()) { log("[scorer-trace] .ctor not resolved"); return false; }
    Interceptor.attach(ctor.ptr, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const target = args[1];
                const dpr = args[2];            // DamagePredictionResult*
                if (target.isNull() || dpr.isNull()) return;
                const targetId = target.add(0x10).readS32();
                utilTrace.targets.push(targetId);   // corrélation: cible de CET event -> l'appel util courant
                // `args[2]` est le struct passé PAR RÉFÉRENCE au ctor : c'est déjà la base
                // des champs, aucun décalage à appliquer. Offsets centralisés (#276).
                const p = readDamagePredictionResult(dpr);
                trace.buf.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    targetId,
                    targetType: target.add(0x14).readS32(),
                    curHealth: p.hpBefore,
                    healthMin: p.healthDmgMin,
                    healthMax: p.healthDmgMax,
                    shieldMin: p.shieldDmgMin,
                    shieldMax: p.shieldDmgMax,
                    limitedByMinHp: p.limitedByMinHp,
                    hits: p.appliedHits,
                    shapeErrors: p.shapeErrors ?? null,
                    casterCol: curPredTile ? curPredTile.col : (curCaster ? curCaster.col : -1),
                    casterRow: curPredTile ? curPredTile.row : (curCaster ? curCaster.row : -1),
                });
            } catch { /* transient — skip */ }
        },
    });
    installed = true;
    log("[scorer-trace] hooked ProbableDamageEvent..ctor @ " + ctor.ptr);
    return true;
}

// ⚠ RVA BUILD-SPÉCIFIQUES — attaches DIFFÉRÉES (armées seulement par scorerDamageTraceOn, PAS au register).
// Toutes les fonctions ci-dessous sont gshared / itérateurs → NON résolubles par findMethod → hookées par
// Adresse hardcodée valide UNIQUEMENT pour le hash `t6dpr4k06g`. Au prochain changement de build, ces RVA
// pointent du CODE ALÉATOIRE et `Interceptor.attach` corromprait le prologue → on N'ATTACHE PAS au register
// (le ctor findMethod ci-dessus, lui, survit au hash et reste auto-armé). RAFRAÎCHIR CES RVA DEPUIS LE DUMP
// À CHAQUE CHANGEMENT DE HASH avant de ré-armer. cf. feedback_rva_transcription_from_va.
let rvaInstalled = false;
/** Ce que CHAQUE sous-hook a réellement obtenu. `rvaInstalled: true` disait seulement « on a
 *  ESSAYÉ » : mesuré le 2026-08-15, il valait `true` pendant que `installElevHook` et
 *  `installLeafHooks` renonçaient tous deux (pins refusés), donc `scorerElevTraceDump` et
 *  `scorerLeafTraceDump` rendaient **0 entrée** — et le seul consommateur de `X_nat` lisait ce
 *  silence comme une mesure. Un booléen d'INTENTION n'est pas un booléen d'ÉTAT. */
const rvaHooks: Record<string, boolean> = {};
function installRvaHooks(): boolean {
    if (rvaInstalled) return true;
    const probe = installedBuild();
    log("[scorer-trace] arming BUILD-SPECIFIC pinned hooks — build chargé = "
        + (probe.build === null ? "NON MESURABLE (" + probe.why + ")" : probe.build));
    rvaHooks.util = installUtilHook();
    rvaHooks.elev = installElevHook();
    rvaHooks.tileTerm = installTileTermHook();
    rvaHooks.leaf = installLeafHooks();
    rvaHooks.composed = installComposedHook();
    rvaHooks.bonus = installBonusHook();
    // #49 : résout la VA concrète de l'override de base (b__0/b__1). Refuse EN BLOC.
    rvaHooks.baseOverride = installBaseOverrideResolver();
    const morts = Object.keys(rvaHooks).filter((k) => !rvaHooks[k]);
    if (morts.length > 0) {
        log("[scorer-trace] SOUS-HOOKS NON POSÉS : " + morts.join(", ")
            + " — leur dump rendra 0 entrée. Un consommateur qui soustrait ces canaux"
            + " (X_nat = Tile7 - Elevation - TileEffects) obtiendra None sur TOUTES les tuiles."
            + " Cause probable : cf. les lignes [build-pin] REFUS ci-dessus.");
    }
    rvaInstalled = true;
    return true;
}

// RVA hook sur la feuille Elevation (itérateur MoveNext) — confirme valeur d'élévation native +
// max/min du domaine pertinent + sortie de feuille, par tuile candidate. Tranche le mystère
// (terme de tuile 26/31/21 non-multiple-de-5 : la feuille ne produit que des multiples de 5).
let elevInstalled = false;
function installElevHook(): boolean {
    if (elevInstalled) return true;
    const ptrFn = pinnedAddress(PIN_ELEVATION_LEAF);
    if (ptrFn === null) return false;
    Interceptor.attach(ptrFn, {
        onEnter(args) {
            const self = this as { _d8?: NativePointer; _stk?: string[] };
            self._d8 = args[0];
            // Backtrace (1ers events) -> révèle l'AGRÉGATEUR qui somme les feuilles de tuile.
            if (trace.on && elevTrace.stacksLeft > 0) {
                try {
                    self._stk = Thread.backtrace(this.context, Backtracer.ACCURATE)
                        .slice(0, 20)
                        .map((a) => {
                            const off = a.sub(il2cppBase);
                            return (off.compare(0) > 0 && off.compare(il2cppBase) < 0)
                                ? "il2cpp+0x" + off.toString(16) : a.toString();
                        });
                } catch { self._stk = undefined; }
            }
        },
        onLeave(retval) {
            if (!trace.on) return;
            // yield=1 -> MoveNext a calculé une valeur fraîche (d__8+0x18) ; 0 -> fin d'itération (stale).
            if (retval.toInt32() !== 1) return;
            try {
                const d8 = (this as { _d8?: NativePointer })._d8;
                if (!d8 || d8.isNull()) return;
                const util = d8.add(0x20).readPointer();
                if (util.isNull()) return;
                const elev = util.add(0x6c).readS32();
                const mx = util.add(0x60).readS32();
                const mn = util.add(0x64).readS32();
                const leaf = Number(BigInt(d8.add(0x18).readS64().toString())) / 4294967296;
                // position candidate : *(d__8+0x28) -> objet, MainTile via +0x18 (cf. décompilé).
                let col = -1, row = -1;
                try {
                    const posObj = d8.add(0x28).readPointer();
                    if (!posObj.isNull()) {
                        const c = decodePos(posObj.add(0x18));
                        if (c) { col = c.col; row = c.row; }
                    }
                } catch { /* col/row optionnel */ }
                const ev: ElevEvent = { seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    col, row, elev, max: mx, min: mn, leaf };
                const stk = (this as { _stk?: string[] })._stk;
                if (stk) { ev.stack = stk; elevTrace.stacksLeft--; }
                elevTrace.buf.push(ev);
            } catch { /* transient — skip */ }
        },
    });
    elevInstalled = true;
    log("[scorer-trace] hooked ElevationUtility leaf (RVA) @ " + ptrFn);
    return true;
}

// RVA hook sur CalculateUtilityFromTilePrediction — capture le TERME DE TUILE COMPLET (composite Tile(7))
// par candidat. Appelée DANS CalculateActionUtility (curCaster déjà posé). Départage : si tile-term ==
// feuille Elevation (50/30/20) → le +24 est dans le DÉGÂT ; sinon une autre feuille de tuile est active.
let tileTermInstalled = false;
function installTileTermHook(): boolean {
    if (tileTermInstalled) return true;
    if (il2cppBase.isNull()) { log("[scorer-trace] il2cppBase null — tileTerm hook skipped"); return false; }
    const ptrFn = resolveSharedPlaybookBody("CalculateUtilityFromTilePrediction");
    if (ptrFn === null) return false;
    Interceptor.attach(ptrFn, {
        onLeave(retval) {
            if (!trace.on) return;
            try {
                // Fix64 (int64 signé) retourné dans RAX. retval = valeur brute (NativePointer).
                let raw = BigInt(retval.toString());
                if (raw >= (1n << 63n)) raw -= (1n << 64n);   // signe
                const tt = Number(raw) / 4294967296;
                tileTermTrace.buf.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                    tileTerm: tt,
                });
            } catch { /* transient — skip */ }
        },
    });
    tileTermInstalled = true;
    log("[scorer-trace] hooked CalculateUtilityFromTilePrediction (RVA) @ " + ptrFn);
    return true;
}

// RVA hooks sur les feuilles candidates au -25 (TileEffects, Contaminated) — capture leur sortie
// yieldée par tuile candidate pour IDENTIFIER laquelle est la feuille -25 active sur (5,3).
let leafInstalled = false;
function installLeafHooks(): boolean {
    if (leafInstalled) return true;
    // Le retour dit ce qui est ATTACHÉ, pas ce qui a été TENTÉ : il valait `true` même quand les
    // DEUX pins étaient refusés, ce qui faisait passer un canal mort pour un canal vide.
    let poses = 0;
    for (const [pin, label] of LEAF_HOOKS) {
        const ptrFn = pinnedAddress(pin);
        if (ptrFn === null) continue;
        poses++;
        Interceptor.attach(ptrFn, {
            onEnter(args) {
                (this as { _d?: NativePointer })._d = args[0];
            },
            onLeave(retval) {
                if (!trace.on) return;
                const ret = retval.toInt32();
                try {
                    const d = (this as { _d?: NativePointer })._d;
                    if (!d || d.isNull()) return;
                    const value = Number(BigInt(d.add(0x18).readS64().toString())) / 4294967296;
                    // Position candidate : selon le layout d'itérateur, l'objet-position est à +0x28 ou
                    // +0x20 (Contaminated inversé). On essaie les deux, MainTile via +0x18.
                    let col = -1, row = -1;
                    for (const off of LEAF_POS_OFFSETS) {
                        try {
                            const posObj = d.add(off).readPointer();
                            if (posObj.isNull()) continue;
                            const c = decodePos(posObj.add(0x18));
                            if (c) { col = c.col; row = c.row; break; }
                        } catch { /* essayer l'offset suivant */ }
                    }
                    leafTrace.buf.push({ seq: ++trace.seq,
                        originRunnerId: getTraceOrigin(),
                        leaf: label, col, row, value, ret });
                } catch { /* transient — skip */ }
            },
        });
        log("[scorer-trace] hooked leaf " + label + " (pinned) @ " + ptrFn);
    }
    leafInstalled = poses > 0;
    return leafInstalled;
}

// RVA hook sur ComposedUtility.MoveNext — énumère les enfants (List<IUtility> @ this+0x18) de chaque
// composite (dédup par ptr this). Identifie les feuilles réellement présentes dans le composite Tile.
let composedInstalled = false;
function installComposedHook(): boolean {
    if (composedInstalled) return true;
    const ptrFn = pinnedAddress(PIN_COMPOSED_UTILITY);
    if (ptrFn === null) return false;
    Interceptor.attach(ptrFn, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const self = args[0].add(0x20).readPointer();   // d__8+0x20 = this (ComposedUtility)
                if (self.isNull()) return;
                const key = self.toString();
                if (composedChildren.seen.has(key)) return;      // une fois par instance
                const list = self.add(0x18).readPointer();        // children List<IUtility>
                if (list.isNull()) return;
                const items = list.add(0x10).readPointer();       // T[] backing
                const count = list.add(0x18).readS32();           // _size
                const names: string[] = [];
                if (!items.isNull() && count > 0 && count < 64) {
                    for (let i = 0; i < count; i++) {
                        const child = items.add(0x20 + i * 8).readPointer();
                        if (child.isNull()) { names.push("<null>"); continue; }
                        try {
                            const klass = child.readPointer();
                            names.push(s(class_get_name(klass) as NativePointer));
                        } catch { names.push("<?>"); }
                    }
                }
                composedChildren.seen.set(key, names);
            } catch { /* transient — skip */ }
        },
    });
    composedInstalled = true;
    log("[scorer-trace] hooked ComposedUtility.MoveNext (RVA) @ " + ptrFn);
    return true;
}

// RVA hook sur GetMultiplierFromDamageBonus — capture chaque bonus % appliqué + backtrace (source
// attaquant/défenseur) + tuile caster. Identifie la source du +50 sur 82 (CS ? défenseur ?) sans deviner.
let bonusInstalled = false;
function installBonusHook(): boolean {
    if (bonusInstalled) return true;
    let poses = 0;                   // ce qui est ATTACHÉ, pas ce qui a été TENTÉ (cf. installLeafHooks)
    for (const pin of PIN_GET_MULT_DMG_BONUS) {
    const ptrFn = pinnedAddress(pin);
    if (ptrFn === null) continue;
    poses++;
    Interceptor.attach(ptrFn, {
        onEnter(args) {
            if (!trace.on) return;
            void args;
            const self = this as { _on?: boolean; _stk?: string[] };
            self._on = true;
            // Backtrace pris à l'ENTRÉE (pile propre du call site) : le RETURN-ADDRESS = le CALL SITE
            // source (att statmods/positional vs def) — LIVRABLE DÉCISIF #49. Gardé au call level.
            if (bonusTrace.stacksLeft > 0) {
                try {
                    self._stk = Thread.backtrace(this.context, Backtracer.ACCURATE)
                        .slice(0, 12)
                        .map((a) => {
                            const off = a.sub(il2cppBase);
                            return (off.compare(0) > 0 && off.compare(il2cppBase) < 0)
                                ? "il2cpp+0x" + off.toString(16) : a.toString();
                        });
                } catch { self._stk = undefined; }
            }
        },
        onLeave(retval) {
            const self = this as { _on?: boolean; _stk?: string[] };
            if (!self._on || !trace.on) return;
            try {
                // GATE ROBUSTE sur le multiplicateur de SORTIE (retval = param_1 out ptr, Fix64 @0) :
                // la branche no-value écrit *param_1=0 -> mult==0 = PAS de bonus (skip). Le Nullable<int>
                // d'ENTRÉE (param_3+0x20) est gshared (get_Value/HasValue via runtime, offset non-fixe) →
                // sa lecture directe est PARASITE (bonus=1) : on ne s'y fie PAS, on dérive le bonus du mult.
                let raw = BigInt(retval.readS64().toString());
                if (raw >= (1n << 63n)) raw -= (1n << 64n);
                const mult = Number(raw) / 4294967296;
                if (mult === 0) return;   // no-value (ou -100% dégénéré) -> pas de modifier applicable
                const bonus = Math.round((mult - 1) * 100);   // 0.70 -> -30 ; 1.50 -> +50 (bonus % entier)
                const ev: BonusEvent = {
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    bonus, mult, hasValue: 1,
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                };
                if (self._stk) { ev.stack = self._stk; bonusTrace.stacksLeft--; }
                bonusTrace.buf.push(ev);
            } catch { /* transient — skip */ }
        },
    });
    log("[scorer-trace] hooked GetMultiplierFromDamageBonus SINGLE (pinned) @ " + ptrFn);
    }
    bonusInstalled = poses > 0;
    return bonusInstalled;
}

// #49 — résolveurs de VA concrète des délégués d'override de base (b__0/b__1). Ciblage pur : lit, pendant
// une prédiction u92 live, la VA que chaque délégué invoque (formule de la base réduite) → décompile après.
let baseOverrideInstalled = false;
function installBaseOverrideResolver(): boolean {
    if (baseOverrideInstalled) return true;
    // Les SIX adresses de ce résolveur sont épinglées ensemble : si l'une est refusée, aucune
    // n'a de sens (b__1 et l'override lisent un `DAT_` du même build). On refuse en BLOC.
    const pb0 = pinnedAddress(PIN_PROFILE_B0);
    const pb1 = pinnedAddress(PIN_PROFILE_B1);
    const pIface = pinnedAddress(PIN_ATTACK_IFACE);
    const pInvoke = pinnedAddress(PIN_FUN_INVOKE);
    const pRetAddr = pinnedAddress(PIN_OVERRIDE_RETADDR);
    const pIfaceDmg = pinnedAddress(PIN_IFACE_DMG);
    if (pb0 === null || pb1 === null || pIface === null
        || pInvoke === null || pRetAddr === null || pIfaceDmg === null) {
        log("[scorer-trace] base-override resolver NON POSÉ — adresses épinglées refusées"
            + " (cf. log [build-pin] REFUS). On n'attache pas en aveugle.");
        return false;
    }
    // b__0 : méthode VIRTUELLE `*(klass + 0x4d8)` de l'instance (param_1+0x10) — slot 58.
    Interceptor.attach(pb0, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const inst = args[0].add(0x10).readPointer();
                if (inst.isNull()) return;
                const klass = inst.readPointer();
                if (klass.isNull()) return;
                const func = klass.add(0x4d8).readPointer();
                if (func.isNull()) return;
                baseOverrideResolved.add("b__0(vtable+0x4d8) -> il2cpp+0x" + func.sub(il2cppBase).toString(16));
            } catch { /* transient */ }
        },
    });
    // b__1 : interface `DAT_1833419e0` idx 0xb5 sur svc = *((param_1+0x10)+0x20) — signature (target, position).
    Interceptor.attach(pb1, {
        onEnter(args) {
            if (!trace.on) return;
            try {
                const ctx = args[0].add(0x10).readPointer();
                if (ctx.isNull()) return;
                const svc = ctx.add(0x20).readPointer();
                if (svc.isNull()) return;
                const klass = svc.readPointer();
                if (klass.isNull()) return;
                const ifaceVal = pIface.readPointer();
                const count = klass.add(0x12e).readU16();
                const itable = klass.add(0xb0).readPointer();
                if (itable.isNull()) return;
                let off = -1;
                for (let i = 0; i < count && i < 300; i++) {
                    const e = itable.add(i * 0x10);
                    if (e.readPointer().equals(ifaceVal)) { off = e.add(8).readS32(); break; }
                }
                if (off < 0) { baseOverrideResolved.add("b__1(iface idx0x" + ATTACK_IFACE_IDX.toString(16) + ") -> IFACE NOT FOUND (count=" + count + ")"); return; }
                const slot = klass.add(0x138).add((off + ATTACK_IFACE_IDX) * 0x10);
                const func = slot.readPointer();
                if (func.isNull()) return;
                baseOverrideResolved.add("b__1(iface+0xb5 off=" + off + ") -> il2cpp+0x" + func.sub(il2cppBase).toString(16));
            } catch { /* transient */ }
        },
    });
    // VRAI override : `FUN_180031990(out, idx 0xd, DAT_18334b2f8, recv)`, appelé depuis
    // `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x17f6`. Hook gaté trace.on + filtré
    // returnAddress (isole CE site — le SECOND call du même invocateur dans PredictAttackRaw porte l'idx
    // 0xe) + resolve-once → non-intrusif. Lit le receiver (R9=args[3] = param_4 de l'invocateur),
    // résout la méthode concrète idx 0xd + son nom de classe, ET capture la valeur override en sortie.
    Interceptor.attach(pInvoke, {
        onEnter(args) {
            if (!trace.on || overrideIdxdResolved) return;
            try {
                if (!this.returnAddress.equals(pRetAddr)) return;
                const idx = args[1].toInt32() & 0xffff;
                const recv = args[3];   // param_4 = R9 = receiver de l'interface
                if (recv.isNull()) return;
                const klass = recv.readPointer();
                if (klass.isNull()) return;
                let recvName = "?";
                try { recvName = s(class_get_name(klass) as NativePointer); } catch { /* */ }
                const ifaceVal = pIfaceDmg.readPointer();
                const count = klass.add(0x12e).readU16();
                const itable = klass.add(0xb0).readPointer();
                let off = -1;
                if (!itable.isNull()) {
                    for (let i = 0; i < count && i < 400; i++) {
                        const e = itable.add(i * 0x10);
                        if (e.readPointer().equals(ifaceVal)) { off = e.add(8).readS32(); break; }
                    }
                }
                if (off < 0) {
                    baseOverrideResolved.add("override idx" + idx + " recv=" + recvName + " -> IFACE NOT FOUND");
                    overrideIdxdResolved = true; return;
                }
                const slot = klass.add(0x138).add((off + idx) * 0x10);
                const func = slot.readPointer();
                if (func.isNull()) return;
                baseOverrideResolved.add("override idx" + idx + " recv=" + recvName
                    + " -> il2cpp+0x" + func.sub(il2cppBase).toString(16));
                overrideIdxdResolved = true;
            } catch { /* transient */ }
        },
    });
    baseOverrideInstalled = true;
    log("[scorer-trace] hooked base-override resolvers b__0/b__1 + idx0xd(FUN_180031990 site-filtered)");
    return true;
}

// Décode une UnitPosition (args = valeur 8B {IList Tiles} OU ptr vers) -> tuile MainTile col/row.
function decodePos(a: NativePointer): { col: number; row: number } | null {
    try {
        for (const list of [a, a.readPointer()]) {
            if (list.isNull()) continue;
            const items = list.add(0x10).readPointer();
            const size = list.add(0x18).readS32();
            if (items.isNull() || size <= 0 || size > 32) continue;
            const tile = items.add(0x20).readPointer();
            if (tile.isNull()) continue;
            const c = readTileCoord(tile);
            if (c.col >= 0 && c.row >= 0) return c;
        }
    } catch { /* */ }
    return null;
}

// RVA hook sur CalculateActionUtility (gshared) — UTILITÉ TOTALE par-candidat + tuile caster (param_4)
// + corrélation cibles (les ProbableDamageEvents produits dans l'appel). onLeave lit le retour
// Nullable<Fix64> (param_1). Le discriminateur du pick (dégât seul insuffisant) est ICI.
let utilInstalled = false;
function installUtilHook(): boolean {
    if (utilInstalled) return true;
    if (il2cppBase.isNull()) { log("[scorer-trace] il2cppBase null — util hook skipped"); return false; }
    const ptrFn = resolveSharedPlaybookBody("CalculateActionUtility");
    if (ptrFn === null) return false;
    Interceptor.attach(ptrFn, {
        onEnter(args) {
            if (!trace.on) return;
            // args = [ret Nullable<Fix64>*, this, p3, position, p5, ability*, ...].
            const self = this as { _ret?: NativePointer; _on?: boolean; _stk?: string[] };
            self._ret = args[0];
            self._on = true;
            curCaster = decodePos(args[3]);
            utilTrace.targets = [];
            // Backtrace (1ers events) : comprendre QUI appelle CalculateActionUtility et où se
            // fait la sélection (argmax / bucket / tri). Offsets rel. il2cppBase -> résoluble ghidra.
            if (utilTrace.stacksLeft > 0) {
                try {
                    self._stk = Thread.backtrace(this.context, Backtracer.ACCURATE)
                        .slice(0, 16)
                        .map((a) => {
                            const off = a.sub(il2cppBase);
                            return (off.compare(0) > 0 && off.compare(il2cppBase) < 0)
                                ? "il2cpp+0x" + off.toString(16) : a.toString();
                        });
                } catch { self._stk = undefined; }
            }
        },
        onLeave() {
            const self = this as { _ret?: NativePointer; _on?: boolean; _stk?: string[] };
            if (!self._on || !trace.on) return;
            try {
                const ret = self._ret;
                if (!ret || ret.isNull()) return;
                // Nullable<Fix64> layout à confirmer : on capte les DEUX candidats Fix64 (@0 et @8).
                const raw0 = Number(BigInt(ret.readS64().toString())) / 4294967296;
                const raw8 = Number(BigInt(ret.add(8).readS64().toString())) / 4294967296;
                const ev: UtilEvent = {
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    casterCol: curCaster ? curCaster.col : -1,
                    casterRow: curCaster ? curCaster.row : -1,
                    targets: utilTrace.targets.slice(),
                    utility: raw8,     // hypothèse : value@8 (fractionnaire observé)
                    hasValue: raw0,    // debug : l'autre candidat
                };
                if (self._stk) { ev.stack = self._stk; utilTrace.stacksLeft--; }
                utilTrace.buf.push(ev);
            } catch { /* */ }
            curCaster = null;
        },
    });
    utilInstalled = true;
    log("[scorer-trace] hooked CalculateActionUtility (RVA) @ " + ptrFn);
    return true;
}

export function register(ctx: Ctx): void {
    // Auto-arm UNIQUEMENT le hook sûr (ProbableDamageEvent.ctor via findMethod, survit au hash). Les hooks
    // RVA build-spécifiques sont armés à la demande par scorerDamageTraceOn (cf. installRvaHooks).
    installHook();   // buffer reste gated par trace.on (défaut false)

    /** ARME la capture. `runnerId` → armement NOMINATIF (seuls les events de CE
     *  runner sont capturés) ; sans lui → armement GLOBAL, le comportement
     *  historique. Cf. game/armed-runners.ts pour l'asymétrie arm/disarm. */
    ctx.rpc.scorerDamageTraceOn = (body?: { runnerId?: number }): Promise<unknown> =>
        queueOnMainThread(() => {
            const ok = installHook();
            installAllModsHook();   // findMethod (nommé) — survit au hash
            installScenarioHook();  // findMethod (nommé) — noyau par-coup (prevHits #49)
            installAttModHook();    // findMethod (nommé) — base-override return[0] + additive @+0x10 (#49)
            installStatModsHook();  // findMethod (nommé) — LE hook négate (args[2]) add vs subtract (#49)
            installModifyHook();    // ValueModification.Modify + backtrace — le GATE du toggle +1298 (#49)
            installPredictBaseHook(); // base pré-spread fed to PredictAttackRaw (context+0x58) (#49)
            installRvaHooks();   // arme les RVA build-spécifiques (l'utilisateur confirme le hash en armant)
            // L'échec d'installation ne doit PAS armer : la porte reflète ce qui est
            // réellement hooké (comportement conservé de `trace.on = ok`).
            if (ok) arm("scorerDamage", body?.runnerId);
            return {
                ok, ...armedReport("scorerDamage", body?.runnerId),
                installed, rvaInstalled, allModsInstalled,
                // ⚠ `rvaInstalled` dit « on a ESSAYÉ », `rvaHooks` dit CE QUI EST ATTACHÉ. Le
                // premier valait `true` avec `elev` et `leaf` morts (pins refusés) — donc les
                // dumps rendaient 0 entrée et `X_nat` valait None partout, en silence. Un
                // consommateur DOIT lire celui-ci avant de conclure quoi que ce soit d'un dump
                // vide. `pinnedAddressRefusals` (RPC `nameResolutionStatus`) donne la cause.
                rvaHooks: { ...rvaHooks },
            };
        });

    /** DÉSARME. `runnerId` → désarme CE runner seulement ; sans lui → désarme le
     *  GLOBAL et **laisse intacts** les armements nominatifs des autres acteurs.
     *  C'est cette asymétrie qui empêche un `finally` d'un probe voisin de tronquer
     *  la capture d'un autre (#483). */
    ctx.rpc.scorerDamageTraceOff = (body?: { runnerId?: number }): unknown => {
        disarm("scorerDamage", body?.runnerId);
        return {
            ok: true, ...armedReport("scorerDamage", body?.runnerId),
            bufferSize: trace.buf.size(),
        };
    };

    ctx.rpc.scorerDamageTraceClear = (
        body?: { stacks?: number; runnerId?: number },
    ): unknown => {
        // runnerId → clear SCOPÉ (drop du bucket de CE runner, les captures
        // des autres acteurs et du live survivent) ; sans → clear GLOBAL.
        const rid = body?.runnerId;
        trace.buf.clear(rid); utilTrace.buf.clear(rid);
        elevTrace.buf.clear(rid); tileTermTrace.buf.clear(rid);
        leafTrace.buf.clear(rid); bonusTrace.buf.clear(rid);
        allModsTrace.buf.clear(rid); scenarioTrace.buf.clear(rid);
        attModTrace.buf.clear(rid); predBaseTrace.buf.clear(rid);
        statModsTrace.buf.clear(rid); modifyTrace.buf.clear(rid);
        if (typeof rid !== "number") {
            trace.seq = 0; utilTrace.targets = [];
            composedChildren.seen.clear();
            baseOverrideResolved.clear(); overrideIdxdResolved = false;   // #49 : re-résout au clear global
        }
        utilTrace.stacksLeft = body?.stacks ?? 6;   // capture les N 1res backtraces après clear
        elevTrace.stacksLeft = body?.stacks ?? 6;   // idem pour la feuille Elevation (-> agrégateur)
        bonusTrace.stacksLeft = body?.stacks ?? 6;   // idem pour les bonus de dégât (-> source att/def)
        modifyTrace.stacksLeft = body?.stacks ?? 12;  // #49 : backtraces des Modify(+1298) -> la fonction-GATE
        return { ok: true, stacksLeft: utilTrace.stacksLeft };
    };

    /** Dump per-candidate ELEVATION leaf (valeur native + max/min domaine pertinent + sortie feuille). */
    ctx.rpc.scorerElevTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), elevInstalled,
            bufferSize: elevTrace.buf.size(),
            entries: elevTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump per-candidate TILE-TERM COMPLET (composite Tile(7) via CalculateUtilityFromTilePrediction). */
    ctx.rpc.scorerTileTermTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), tileTermInstalled,
            bufferSize: tileTermTrace.buf.size(),
            entries: tileTermTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump per-candidate SORTIE des feuilles situationnelles hookées (TileEffects/Contaminated). */
    ctx.rpc.scorerLeafTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), leafInstalled,
            bufferSize: leafTrace.buf.size(),
            entries: leafTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump les bonus de dégât capturés (valeur % + tuile caster + backtrace source att/def). */
    ctx.rpc.scorerBonusTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), bonusInstalled,
            bufferSize: bonusTrace.buf.size(),
            entries: bonusTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** #49 : dump la base pré-spread fed to PredictAttackRaw (context+0x58) par tuile. */
    ctx.rpc.scorerPredBaseDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 8000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), predBaseInstalled,
            bufferSize: predBaseTrace.buf.size(),
            entries: predBaseTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** #49 : dump le base-override (return[0]) capturé de CalculateAttackerModifiersForPrediction par tuile. */
    ctx.rpc.scorerAttModDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 4000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), attModInstalled,
            bufferSize: attModTrace.buf.size(),
            entries: attModTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** #49 : dump CalculateModifiersFromStatModifications — negate(add/subtract) + Initial + listCount par tuile. */
    ctx.rpc.scorerStatModsDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 8000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), statModsInstalled,
            bufferSize: statModsTrace.buf.size(),
            entries: statModsTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** #49 : dump ValueModification.Modify (amount>=500) + backtrace — la fonction-GATE du toggle +1298. */
    ctx.rpc.scorerModifyDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 4000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), modifyInstalled,
            bufferSize: modifyTrace.buf.size(),
            entries: modifyTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** #49 : dump les VA concrètes résolues des délégués d'override de base (b__0 vtable / b__1 iface). */
    ctx.rpc.scorerBaseOverrideDump = (): unknown => {
        return { ...armedReport("scorerDamage"), baseOverrideInstalled, resolved: Array.from(baseOverrideResolved) };
    };

    /** Dump les enfants (noms de classe) de chaque ComposedUtility vu — identifie les feuilles du composite. */
    ctx.rpc.scorerComposedDump = (): unknown => {
        const composites = Array.from(composedChildren.seen.entries())
            .map(([ptr, children]) => ({ ptr, count: children.length, children }));
        return { ...armedReport("scorerDamage"), composedInstalled, composites };
    };

    /** Dump des appels CalculateBaseDamageWithAllModifiers (input/isCrit/isMelee/output/site). */
    ctx.rpc.scorerAllModsTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), allModsInstalled,
            bufferSize: allModsTrace.buf.size(),
            entries: allModsTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump per-candidate TOTAL utility (CalculateActionUtility) — le discriminateur du pick. */
    ctx.rpc.scorerUtilTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), utilInstalled,
            bufferSize: utilTrace.buf.size(),
            entries: utilTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump des appels CalculateDamagePredictionScenario (rawMin/Max, prevHits, prob, outMin/Max) —
     *  noyau par-coup ; prevHits = la reduction per-cible #49 non lisible statiquement. */
    ctx.rpc.scorerScenarioTraceDump = (
        body?: { max?: number; runnerId?: number },
    ): unknown => {
        const max = body?.max ?? 2000;
        return {
            ...armedReport("scorerDamage", body?.runnerId), scenarioInstalled,
            bufferSize: scenarioTrace.buf.size(),
            entries: scenarioTrace.buf.entries(body?.runnerId).slice(-max),
        };
    };

    /** Dump captured events. Body: { since?: seq, max?: number }. */
    ctx.rpc.scorerDamageTraceDump = (
        body?: { since?: number; max?: number; runnerId?: number },
    ): unknown => {
        const since = body?.since ?? 0;
        const max = body?.max ?? 2000;
        let filtered = trace.buf.entries(body?.runnerId);
        if (since > 0) filtered = filtered.filter((e) => e.seq > since);
        return {
            ...armedReport("scorerDamage", body?.runnerId), installed, totalSeq: trace.seq,
            bufferSize: trace.buf.size(), returned: Math.min(filtered.length, max),
            entries: filtered.slice(-max),
        };
    };
}
