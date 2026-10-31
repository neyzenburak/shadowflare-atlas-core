"""Octilinear routes in projected screen space, checked in real world space."""
import heapq
import math

DIRECTIONS = ((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))


def project(point, scale):
    x,y=point;mx,my=scale
    return ((x-y)*mx/100,(x+y)*my/100)


def unproject(point, scale):
    u,v=point;mx,my=scale
    a=u*100/mx;b=v*100/my
    return ((a+b)/2,(b-a)/2)


def link(a,b):
    """Two possible exact 45/90 degree connectors, including short endpoints."""
    dx=b[0]-a[0];dy=b[1]-a[1];n=min(abs(dx),abs(dy))
    sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1
    p=(a[0]+sx*n,a[1]+sy*n)
    q=(b[0]-sx*n,b[1]-sy*n)
    return ([a,p,b],[a,q,b])


def simplify(points):
    out=[]
    for p in points:
        p=tuple(p)
        if out and math.dist(out[-1],p)<1e-6:continue
        if len(out)>=2:
            a,b=out[-2:];u=(b[0]-a[0],b[1]-a[1]);v=(p[0]-b[0],p[1]-b[1])
            if abs(u[0]*v[1]-u[1]*v[0])<1e-6 and u[0]*v[0]+u[1]*v[1]>0:out.pop()
        out.append(p)
    return out


def turn_ok(a,b,c):
    u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
    return u[0]*v[0]+u[1]*v[1]>=-1e-6


def heading(a,b):
    return round(math.atan2(b[1]-a[1],b[0]-a[0])/(math.pi/4))%8


def prefix(points,distance):
    out=[points[0]]
    for a,b in zip(points,points[1:]):
        n=math.dist(a,b)
        if distance<=n:
            out.append(along([a,b],distance));return simplify(out)
        out.append(b);distance-=n
    return simplify(out)


def find_route(start,target,clear,step=12,max_nodes=100000,initial_heading=8):
    """A* with heading state; turns are 45/90 degrees, never corner cutting.

    clear(a,b) tests the entire segment, not just its endpoint. The lattice
    lives in projected pixels so isometric tiles do not distort beam angles.
    """
    start=tuple(start);target=tuple(target)
    def point(k):return (start[0]+k[0]*step,start[1]+k[1]*step)
    def heuristic(p):
        x=abs(target[0]-p[0])/step;y=abs(target[1]-p[1])/step
        return max(x,y)+(math.sqrt(2)-1)*min(x,y)
    origin=(0,0,initial_heading);cost={origin:0};parent={};queue=[(heuristic(start),0,origin)];serial=0
    edges={};visited=0
    while queue and visited<max_nodes:
        _,g,k=heapq.heappop(queue)
        if g!=cost.get(k):continue
        visited+=1;p=point(k)
        if math.dist(p,target)<=step*2:
            for tail in link(p,target):
                tail=simplify(tail)
                if k[2]!=8 and len(tail)>1:
                    dx,dy=DIRECTIONS[k[2]]
                    if not turn_ok((p[0]-dx,p[1]-dy),p,tail[1]):continue
                if all(turn_ok(*tail[i:i+3]) for i in range(len(tail)-2)) and all(clear(a,b) for a,b in zip(tail,tail[1:])):
                    chain=[];at=k
                    while at in parent:chain.append(point(at));at=parent[at]
                    return simplify([start]+list(reversed(chain))+tail[1:])
        for direction,(dx,dy) in enumerate(DIRECTIONS):
            if k[2]!=8 and min((direction-k[2])%8,(k[2]-direction)%8)>2:continue
            nxt=(k[0]+dx,k[1]+dy,direction);q=point(nxt)
            edge=(k[:2],nxt[:2]);valid=edges.get(edge)
            if valid is None:
                valid=clear(p,q);edges[edge]=valid;edges[(edge[1],edge[0])]=valid
            if not valid:continue
            value=g+(math.sqrt(2) if dx and dy else 1)+(0.55 if k[2] not in (8,direction) else 0)
            if value>=cost.get(nxt,math.inf):continue
            parent[nxt]=k;cost[nxt]=value;serial+=1
            heapq.heappush(queue,(value+heuristic(q),value,nxt))
    return None


def wall_route(start,target,clear):
    """When no route exists, end immediately before the first obstacle."""
    out=[tuple(start)]
    for a,b in zip(link(start,target)[0],link(start,target)[0][1:]):
        n=max(1,math.ceil(math.dist(a,b)/2));last=a
        for i in range(1,n+1):
            p=(a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n)
            if not clear(last,p):return simplify(out+[last])
            last=p
        out.append(b)
    return simplify(out)


def along(points,distance):
    for a,b in zip(points,points[1:]):
        length=math.dist(a,b)
        if distance<=length:
            return (a[0]+(b[0]-a[0])*distance/max(length,1e-9),a[1]+(b[1]-a[1])*distance/max(length,1e-9))
        distance-=length
    return points[-1]


def length(points):return sum(math.dist(a,b) for a,b in zip(points,points[1:]))


def deadline_distance(distance,total,previous,now,deadline):
    """Reach the remaining route by one fixed deadline, including replans."""
    delta=max(0,now-previous);remaining=max(0,deadline-now)
    fraction=1 if remaining<=0 else min(1,delta/(remaining+delta))
    return min(total,distance+(total-distance)*fraction)
