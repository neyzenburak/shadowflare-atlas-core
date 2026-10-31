"""Procedural native DIB sprites. No overlay or external image dependency."""
from functools import lru_cache
import math

# width, height, anchor x/y, animation frame count
SPECS={'meteor':(72,112,36,84,8),'blast':(128,96,64,64,8),
       'fire':(96,96,48,82,8),'missile':(64,112,32,84,8),
       'nuke':(192,160,96,112,8),'mushroom':(192,224,96,205,12)}


def gaussian(x,y,sx,sy):return math.exp(-x*x/sx-y*y/sy)


@lru_cache(maxsize=52)
def pixels(kind,frame):
    w,h,ax,ay,frames=SPECS[kind];phase=frame/frames;t=frame/max(1,frames-1)
    out=bytearray(w*h*3)
    for y in range(h):
        for x in range(w):
            dx=x-ax;dy=y-ay;red=green=blue=0.0
            if kind=='meteor':
                r=math.hypot(dx,dy);rock=max(0,1-r/10)
                core=gaussian(dx,dy,90,65)
                tail=gaussian(dx-dy*.28,dy+29,65,1600)*max(0,min(1,-dy/12))
                flicker=.8+.2*math.sin(dx*.7+dy*.3+phase*6.28)
                red=core*260+tail*210*flicker+rock*90
                green=core*180+tail*88*flicker+rock*75
                blue=core*65+tail*18+rock*65
            elif kind=='missile':
                body=abs(dx)<5 and -28<=dy<=10
                nose=10<dy<24 and abs(dx)<(24-dy)*.4
                wing=-30<dy<-15 and abs(dx)<16-abs(dy+23)
                red=190*body+225*nose+160*wing;green=200*body+30*nose+170*wing;blue=215*body+30*nose+180*wing
                exhaust=gaussian(dx,dy+48,35,700)*(.75+.25*math.sin(phase*6.28+dy*.2))
                red+=250*exhaust;green+=115*exhaust;blue+=30*exhaust
            elif kind in ('blast','nuke'):
                big=kind=='nuke';r=math.hypot(dx,dy*(1.35 if big else 1.6))
                radius=5+t*(85 if big else 57)
                ring=math.exp(-((r-radius)/max(2,7*(1-t)))**2)*(1-t*.8)
                glow=math.exp(-r*r/max(30,(radius*.6)**2))*(1-t)**.6
                rays=max(0,math.cos(math.atan2(dy,dx)*8+frame*.2))**8*glow*.35
                red=(ring*.8+glow+rays)*255;green=(ring*.42+glow*.8+rays)*255;blue=(ring*.12+glow*.44+rays)*255
            elif kind=='fire':
                floor=gaussian(dx,dy,1250,80)*.6
                flame=0.0;hot=0.0
                for k in range(5):
                    cx=(k-2)*12+math.sin(phase*6.28+k*1.8)*4
                    height=25+13*math.sin(phase*6.28+k*2.1)
                    flame+=gaussian(dx-cx+(dy+height/2)*.12,dy+height/2,40,240+height*4)
                    hot+=gaussian(dx-cx,dy+7,30,90)
                fade=max(0,min(1,(8-dy)/8))
                red=(flame*.9+floor)*255*fade;green=(flame*.3+hot*.52+floor*.35)*255*fade;blue=hot*45*fade
            elif kind=='mushroom':
                rise=math.sin(t*math.pi/2);fade=min(1,(1-t)*4+.12)
                cap_y=ay-60-105*rise;cap_width=28+43*rise
                cloud=0.0
                for k in range(7):
                    angle=k*2.399;cx=ax+math.cos(angle)*cap_width*.55
                    cy=cap_y+math.sin(angle)*18
                    cloud+=gaussian(x-cx,y-cy,cap_width*cap_width*.28,380+rise*160)*.28
                stem=gaussian(dx,y-(ay+cap_y)/2,120+rise*45,max(300,((ay-cap_y)/2)**2))*.58
                base=gaussian(dx,dy,2800,180)*.4
                texture=.78+.22*math.sin(x*.19+y*.24+frame*.8)*math.cos(x*.11-y*.16)
                fire=gaussian(dx,y-cap_y,cap_width*cap_width*.6,700)*(1-t)*.8
                value=(cloud*texture+stem+base)*fade
                red=value*165+fire*255;green=value*137+fire*120;blue=value*116+fire*35
            at=((h-1-y)*w+x)*3
            out[at:at+3]=bytes((max(0,min(255,round(blue))),max(0,min(255,round(green))),max(0,min(255,round(red)))))
    return bytes(out)


def visual_groups(targets,scale,cell=26):
    """Coincident flames/clouds share one visual; damage keeps every unique ID."""
    groups={}
    for target in targets:
        x,y=target['xy'];u=(x-y)*scale[0]/100;v=(x+y)*scale[1]/100
        key=(math.floor(u/cell),math.floor(v/cell))
        groups.setdefault(key,target)
    return list(groups.values())
