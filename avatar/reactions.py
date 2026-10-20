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
}
ALIASES={'excited':'happy','love':'shy','teasing':'happy','concerned':'sad','defeated':'sad',
         'flustered':'shy','shocked':'surprised'}


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
