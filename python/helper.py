'''
  Some helper stuff and conversion functions
'''

class Dict2Class(object):
  ''' Mock a class from a dictionary '''
  def __init__(self, my_dict:dict) -> None:
    for key in my_dict:
      setattr(self, key, my_dict[key])

def ft2km(ft:float) -> float:
  return ft/3280.84

def kts2kmh(kts:float) -> float:
  return kts*1.852

def hsv2rgb(hsv:tuple) -> str:
    h,s,v = hsv
    
    h8 = h*8
    hi = int(h8)
    f  = h8 - hi
    
#    p  = v * (1.0 - s)
#    q  = v * (1.0 - s * f)
#    t  = v * (1.0 - s * (1.0 - f))
    vs  = v * s
    vsf = vs * f
    p   = v - vs
    q   = v - vsf
    t   = v - vs + vsf
    
    if (hi == 0):
        r = v
        g = t
        b = p
    elif (hi == 1):
        r = q
        g = v
        b = p
    elif (hi == 2):
        r = p
        g = v
        b = t
    elif (hi == 3):
        r = p
        g = q
        b = v
    elif (hi == 4):
        r = t
        g = p
        b = v
    else:
        r = v
        g = p
        b = q
    
    #return np.array([r,g,b])
    return f"#{int(255*r):02X}{int(255*g):02X}{int(255*b):02X}"

