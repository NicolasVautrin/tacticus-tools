# Knowledge — Pieges resolus & lessons learned

## Position boxed vs unboxed (MoveUnitMessage)

**Probleme** : `List<Position>.Add` via `invokeMethod` passait le pointeur boxe au lieu des donnees brutes. Le jeu ignorait silencieusement le MoveUnitMessage.

**Symptome** : `UnitFeetPositions: [1116365920]` (adresse pointeur) au lieu de `[4]` (valeur Column).

**Fix** : `createPositionUnboxed(col, row)` retourne un buffer brut de 8 bytes (Column 4B + Row 4B). Pour `il2cpp_runtime_invoke`, les value types doivent etre passes comme pointeur vers les donnees brutes, pas comme objet boxe.

```javascript
function createPositionUnboxed(col, row) {
    var buf = Memory.alloc(8);
    buf.writeS32(col);
    buf.add(4).writeS32(row);
    return buf;
}
```

## Same-thread suppression Frida

**Probleme** : `Interceptor.attach` supprime les hooks imbriques sur le meme thread. Les hooks sur StreamDispatcher et MoveUnitOperation ne se declenchent pas quand appeles depuis un callback attach sur Update.

**Verification** : Gemini a confirme, Codex a dit le contraire (incorrect).

**Fix** : `Interceptor.replace` sur `IdunGameViews.Update` au lieu de `Interceptor.attach`. Le code dans un replace est traite comme la fonction native, pas un callback.

**Attention** : `traps: 'all'` est pour Stalker, pas Interceptor. Ne resout PAS ce probleme et cause des crashes avec replace.

## findMethod overload

**Probleme** : `findMethod(klass, ".ctor")` retourne le PREMIER match. Pour les classes avec plusieurs constructeurs (parameterless + parameterized), on peut appeler le mauvais .ctor avec des args null.

**Fix** : Pour les messages (MoveUnitMessage, etc.), utiliser `il2cpp_object_new(klass)` sans appeler .ctor. L'objet est alloue avec des champs a zero, puis on ecrit les champs directement.

## Runner capture

**Probleme** : Avant, il fallait jouer un tour (hook Apply) pour capturer le runner.

**Fix** : `IdunGameViews._runner` donne acces direct au runner. Capture au premier frame Update via `self.add(_gvRunnerOff).readPointer()`.

## ARM64 HFA convention

`Vector3` (3 floats) passe dans les registres float (s0, s1, s2), pas les registres integer. Pour `HandleMouseButtonUpThisFrame(Vector3, IEntity, IEntity)`, les args sont : `args[0]=this, args[1]=entityHit, args[2]=tileHit`.

## Interceptor.revert / revertAll

**N'existent PAS** en Frida 17.9.1. Le graceful cleanup fonctionne quand meme via le pattern cleanup message + sleep 50ms + unload.

## Reinjectoin et sessions

- Une nouvelle injection (`POST /api/scripts/run`) stop automatiquement toutes les sessions courantes via `stop_all()`.
- Ne JAMAIS appeler `stop` manuellement — ca crash le jeu en detachant le replace pendant un frame.
- Si "already replaced this function" apparait, le process a un replace orphelin. Relancer le jeu.
- Le `--reload` d'uvicorn perd les sessions en memoire (le singleton `_manager` est reinitialise). Apres un reload, `stop_all()` ne trouve rien.

## APIs IL2CPP

Exports verifies :
```
il2cpp_domain_get, il2cpp_domain_get_assemblies, il2cpp_assembly_get_image
il2cpp_class_get_name, il2cpp_class_get_namespace, il2cpp_class_get_methods
il2cpp_class_get_fields, il2cpp_class_is_enum, il2cpp_class_is_valuetype
il2cpp_class_instance_size, il2cpp_class_from_type
il2cpp_field_get_name, il2cpp_field_get_offset, il2cpp_field_get_type
il2cpp_object_new, il2cpp_runtime_invoke
```

**ABSENT** : `il2cpp_type_get_class` -> utiliser `il2cpp_class_from_type`

## readDict — serialisation des valeurs de dictionnaires

**Probleme** : `readDict` dans `il2cpp-serializer.js` lisait toutes les valeurs avec `readS32()`. Pour les `Dictionary<EnumType, string[]>` ou `Dictionary<K, string>`, ca retournait des pointeurs bruts au lieu des vraies valeurs.

**Fix** : introspection du type de la value via `field_get_type` sur le champ `value` de l'`Entry` struct, puis appel a `readFieldValue()` au lieu de `readS32()`. Les strings, arrays et objets sont maintenant correctement deserialisés.

## Enum resolution dans les reponses RPC

**Probleme** : les enums dans `_events` n'etaient pas resolus (`_value` sans `_name`).

**Cause** : les `rpc_response` etaient interceptees dans `on_message` et retournees directement via le Future sans passer par `enrich_payload`. Apres un `uvicorn --reload`, le singleton `_resolver` est reinitialise — il faut un restart propre du backend.

**Fix** : appeler `resolver.enrich_payload(result)` avant de resoudre le Future dans `frida_manager.py`. Le resolver est recursif et descend dans les `_events` imbriques.

## AI observer hooks — prudence

Les hooks `Interceptor.attach` sur les services IA (`AttackQuery`, `DamagePredictionQuery`, `TargetingQuery`) crashent le jeu si on :
- Serialise le `retval` dans `onLeave` (objets temporaires, struct value types)
- Lit des args sur le mauvais overload (`findMethod` retourne le premier match)

**Approche safe** : hooks minimaux (juste `send()` dans `onEnter`), puis ajouter les lectures une par une. `retval.toInt32()` est safe pour bool/int.
