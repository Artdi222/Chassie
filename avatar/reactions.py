"""Subtle per-model reactions using only each package's actual Cubism parameters."""
REACTIONS = {
    'happy': {'ParamMouthForm':.75,'ParamEyeLSmile':.45,'ParamEyeRSmile':.45,'ParamCheek':.25},
    'sad': {'ParamMouthForm':-.4,'ParamBrowLForm':-.45,'ParamBrowRForm':-.45,'ParamBrowLY':-.2,'ParamBrowRY':-.2},
    'thinking': {'ParamBrowLY':.2,'ParamBrowRY':-.15,'ParamMouthForm':.1},
    'curious': {'ParamBrowLY':.35,'ParamBrowRY':.35,'ParamMouthForm':.25},
    'surprised': {'ParamBrowLY':.65,'ParamBrowRY':.65,'ParamMouthForm':-.2},
    'angry': {'ParamBrowLAngle':-.65,'ParamBrowRAngle':-.65,'ParamBrowLY':-.25,'ParamBrowRY':-.25,'ParamMouthForm':-.35},
    'shy': {'ParamCheek':.65,'ParamMouthForm':.45,'ParamEyeLSmile':.25,'ParamEyeRSmile':.25},
    'sleepy': {'ParamEyeLOpen':.45,'ParamEyeROpen':.45,'ParamMouthForm':.1},
    'excited': {'ParamMouthForm':1,'ParamEyeLSmile':.6,'ParamEyeRSmile':.6,'ParamBrowLY':.4,'ParamBrowRY':.4,'ParamCheek':.35},
    'love': {'ParamMouthForm':.6,'ParamEyeLSmile':.8,'ParamEyeRSmile':.8,'ParamCheek':.8},
    # Param48 is the package's crooked-mouth smirk; one smiling eye reads as a wink-like tease.
    'teasing': {'Param48':1,'ParamMouthForm':.4,'ParamEyeLSmile':.55,'ParamBrowRY':.3},
    'concerned': {'ParamBrowLForm':-.3,'ParamBrowRForm':-.3,'ParamBrowLAngle':.35,'ParamBrowRAngle':.35,'ParamMouthForm':-.2},
    'defeated': {'ParamEyeLOpen':.55,'ParamEyeROpen':.55,'ParamBrowLY':-.35,'ParamBrowRY':-.35,'ParamBrowLForm':-.5,'ParamBrowRForm':-.5,'ParamMouthForm':-.55},
    # Param46 puffs the cheeks.
    'flustered': {'ParamCheek':1,'Param46':.6,'ParamBrowLY':.25,'ParamBrowRY':.25,'ParamMouthForm':-.1},
    # Param49 is the package's wide-eyed stare.
    'shocked': {'Param49':1,'ParamBrowLY':.9,'ParamBrowRY':.9,'ParamMouthForm':-.5},
}
# DeepSeek-chan (VBridger/ARKit rig): no ParamCheek/EyeSmile pair or brow form, but it ships
# toggles: key1 dark face, key2 tears, key4 heart eyes, key5 >< eyes, key7 blush, key9 fang,
# key13 cold sweat. Its Param46/48/49 are grass physics, so Tian Muzi's table must not apply.
# DeepSeek-chan also uses the package's own toggles: key2 tears, key3 swirl eyes,
# key6 smug eyes, key8 loading icon, Movement3 raised index finger, LeanInput lean.
DEEPSEEK_REACTIONS = {
    'happy': {'ParamMouthForm':.7,'EyeSmile':.6,'MouthSmile_L':.5,'MouthSmile_R':.5},
    'sad': {'ParamMouthForm':-.4,'BrowInnerUp':.7,'ParamBrowLY':-.2,'ParamBrowRY':-.2,'key2':.8},
    'thinking': {'ParamBrowLY':.2,'ParamBrowRY':-.15,'ParamMouthForm':.1,'MouthX':.3,'Movement3':1},
    'waiting': {'ParamBrowLY':.2,'ParamBrowRY':-.15,'ParamMouthForm':.1,'MouthX':.3,'key8':1},
    'curious': {'ParamBrowLY':.35,'ParamBrowRY':.35,'ParamMouthForm':.25,'LeanInput':-20},
    'surprised': {'ParamBrowLY':.65,'ParamBrowRY':.65,'ShockL':.5,'ShockR':.5,'ParamMouthForm':-.2},
    'angry': {'ParamBrowLAngle':-.65,'ParamBrowRAngle':-.65,'ParamBrowLY':-.25,'ParamBrowRY':-.25,'ParamMouthForm':-.35,'key1':.6},
    'shy': {'key7':.8,'ParamMouthForm':.45,'EyeSmile':.3},
    'sleepy': {'ParamEyeLOpen':.45,'ParamEyeROpen':.45,'ParamMouthForm':.1},
    'excited': {'ParamMouthForm':1,'EyeSmile':.7,'MouthSmile_L':.8,'MouthSmile_R':.8,'ParamBrowLY':.4,'ParamBrowRY':.4,'key7':.35,'LeanInput':-15},
    'love': {'key4':1,'key7':.8,'ParamMouthForm':.6},
    'teasing': {'key9':1,'key6':1,'MouthSmile_L':.8,'ParamMouthForm':.4,'ParamBrowRY':.3},
    'concerned': {'BrowInnerUp':.7,'ParamBrowLAngle':.35,'ParamBrowRAngle':.35,'ParamMouthForm':-.2,'key13':.6,'LeanInput':-12},
    'defeated': {'ParamEyeLOpen':.55,'ParamEyeROpen':.55,'BrowInnerUp':.6,'ParamBrowLY':-.35,'ParamBrowRY':-.35,'ParamMouthForm':-.55,'key13':1,'key2':.5},
    'flustered': {'key7':1,'key5':1,'CheeckPuff':.6,'ParamBrowLY':.25,'ParamBrowRY':.25,'key13':.5},
    'shocked': {'key3':1,'ParamBrowLY':.9,'ParamBrowRY':.9,'ParamMouthForm':-.5,'key13':.7},
}
MODEL_REACTIONS={'Model_4':REACTIONS,'DeepSeek':DEEPSEEK_REACTIONS}
ALIASES={}


# A model without its own status reaction falls back to the closest emotion.
FALLBACKS={'waiting':'thinking'}


def expression_id(emotion, generated=None):
    """Reaction file for an emotion; with the model's generated table, fall back when missing."""
    name=ALIASES.get(emotion,emotion)
    if generated is not None and f'__chassie__/{name}.exp3.json' not in generated:
        name=FALLBACKS.get(name,name)
    return f'__chassie__/{name}.exp3.json' if any(name in table for table in MODEL_REACTIONS.values()) else None


def generated_reactions(parameter_ids, model_id='Model_4'):
    """Empty for packages without a reaction table: their own expressions stay manual."""
    result={}
    for name,values in MODEL_REACTIONS.get(model_id,{}).items():
        result[expression_id(name)]={'Type':'Live2D Expression','FadeInTime':.25,'FadeOutTime':.2,
            'Parameters':[{'Id':key,'Value':value,'Blend':'Multiply' if key in ('ParamEyeLOpen','ParamEyeROpen') else 'Overwrite'}
                          for key,value in values.items() if key in parameter_ids]}
    return result
