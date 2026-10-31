"""Screen geometry in the original game's 640x480 coordinate space."""


def validate_size(width,height):
    if any(isinstance(v,bool)or not isinstance(v,int)for v in (width,height)):
        raise ValueError('Çözünürlük genişliği ve yüksekliği tam sayı olmalı.')
    if not 640<=width<=7680 or not 480<=height<=4320:
        raise ValueError('Çözünürlük 640×480 ile 7680×4320 arasında olmalı.')
    return width,height


def geometry(width,height):
    validate_size(width,height)
    return dict(width=width,height=height,halfWidth=width//2,halfHeight=height//2,
                dx=width//2-320,dy=height-480,zero=0)
