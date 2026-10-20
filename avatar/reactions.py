"""Subtle model-four reactions using only its actual Cubism parameters."""
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
ALIASES={}


def expression_id(emotion):
    name=ALIASES.get(emotion,emotion)
    return f'__chassie__/{name}.exp3.json' if name in REACTIONS else None


def generated_reactions(parameter_ids):
    result={}
    for name,values in REACTIONS.items():
        result[expression_id(name)]={'Type':'Live2D Expression','FadeInTime':.25,'FadeOutTime':.2,
            'Parameters':[{'Id':key,'Value':value,'Blend':'Multiply' if key in ('ParamEyeLOpen','ParamEyeROpen') else 'Overwrite'}
                          for key,value in values.items() if key in parameter_ids]}
    return result
