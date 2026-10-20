"""Validated interaction preferences shared by desktop and browser renderers."""
import math

DEFAULT_INTERACTION = {'gaze_enabled': True, 'gaze_radius': 180, 'follow_speed': 1.,
                       'headpat_enabled': True, 'headpat_delay': .18}


def interaction_settings(data=None):
    if data is None:return dict(DEFAULT_INTERACTION)
    if not isinstance(data,dict) or set(data)-set(DEFAULT_INTERACTION):
        raise ValueError('Unknown interaction setting')
    result={**DEFAULT_INTERACTION,**data}
    for key in ('gaze_enabled','headpat_enabled'):
        if type(result[key]) is not bool:raise ValueError(f'{key} must be boolean')
    for key,low,high in (('gaze_radius',40,400),('follow_speed',.5,2),('headpat_delay',.15,1)):
        value=result[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'{key} must be between {low} and {high}')
    return result
