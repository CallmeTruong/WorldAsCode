"""Provider-neutral numeric surface compiler; no city-specific forms or palette."""
import math
import numpy as np
from pyproj import Transformer
from shapely import constrained_delaunay_triangles,make_valid
from shapely.geometry import Polygon,Point,MultiPoint,box
from shapely.ops import triangulate
from .data import polygons


class LocalFrame:
    def __init__(self,origin,ground_height):
        self.origin=origin;self.ground=float(ground_height)
        self.to_xy=Transformer.from_crs(4326,origin['projection'],always_xy=True)
        self.from_xy=Transformer.from_crs(origin['projection'],4326,always_xy=True)
        self.to_ecef=Transformer.from_crs(4979,4978,always_xy=True)
        self.e,self.n=self.to_xy.transform(origin['longitude'],origin['latitude'])
        center=np.array(self.to_ecef.transform(origin['longitude'],origin['latitude'],self.ground))
        lon,lat=self.from_xy.transform(self.e+1,self.n);east=np.array(self.to_ecef.transform(lon,lat,self.ground))-center
        lon,lat=self.from_xy.transform(self.e,self.n-1);south=np.array(self.to_ecef.transform(lon,lat,self.ground))-center
        up=np.array(self.to_ecef.transform(origin['longitude'],origin['latitude'],self.ground+1))-center
        self.basis=np.column_stack([east/np.linalg.norm(east),up/np.linalg.norm(up),south/np.linalg.norm(south)])
        self.center=center

    def lonlat(self,xz):
        p=np.asarray(xz,float);lon,lat=self.from_xy.transform(self.e+p[:,0],self.n-p[:,1]);return np.column_stack([lon,lat]).tolist()

    def ecef(self,xyz):
        p=np.asarray(xyz,float);lon,lat=self.from_xy.transform(self.e+p[:,0],self.n-p[:,2]);x,y,z=self.to_ecef.transform(lon,lat,p[:,1]+self.ground);return np.column_stack([x,y,z])

    def local_camera(self,camera):
        x,z=self.to_xy.transform(camera['longitude'],camera['latitude'])
        return {'position':[x-self.e,camera['height']-self.ground,self.n-z],
                'direction':np.linalg.solve(self.basis,np.asarray(camera['direction_ecef'])).tolist(),
                'up':np.linalg.solve(self.basis,np.asarray(camera['up_ecef'])).tolist(),
                'fov':math.degrees(2*math.atan(1/camera['projection_matrix'][5])),
                'aspect':camera['viewport'][0]/camera['viewport'][1]}


def sample_plan(city,spacing=2.5,max_samples=6000):
    area=sum(b['area'] for b in city['buildings']);step=max(spacing,math.sqrt(area/max_samples))
    plans=[]
    for b in city['buildings']:
        poly=make_valid(Polygon(b['outer'],b['holes']));inner=poly.buffer(-.5)
        if inner.is_empty:inner=poly
        x0,z0,x1,z1=poly.bounds;points=[]
        for x in np.arange(x0+step*.35,x1,step):
            for z in np.arange(z0+step*.35,z1,step):
                if inner.contains(Point(x,z)):points.append([float(x),float(z)])
        if not points:
            q=poly.representative_point();points=[[q.x,q.y]]
        plans.append({'id':b['id'],'points':points,'spacing':step})
    return plans


class RoofField:
    def __init__(self,points,heights,fallback):
        p=np.asarray(points,float);h=np.asarray(heights,float)
        valid=np.isfinite(h)&(h>=2)&(h<=500)
        self.points=p[valid];self.heights=h[valid];self.fallback=fallback

    def values(self,queries,regularized=False):
        result=[]
        for q in np.asarray(queries,float):
            if len(self.points)==0:result.append(float(self.fallback));continue
            distances=np.sum((self.points-q)**2,axis=1);k=min(12,len(distances));indices=np.argpartition(distances,k-1)[:k];indices=indices[np.argsort(distances[indices])]
            nearest=indices[0]
            if not regularized and distances[nearest]<1e-10:result.append(float(self.heights[nearest]));continue
            # Preserve podium/tower steps instead of averaging unrelated levels.
            indices=indices[np.abs(self.heights[indices]-self.heights[nearest])<3]
            if not regularized:indices=indices[:3]
            if len(indices)>=3:
                a=np.column_stack([self.points[indices]-q,np.ones(len(indices))]);h=self.heights[indices]
                coeff=np.linalg.lstsq(a,h,rcond=None)[0]
                for _ in range(2 if regularized else 0):
                    residual=np.abs(a@coeff-h);keep=residual<max(.25,float(np.median(residual))*2.5)
                    if sum(keep)<3:break
                    coeff=np.linalg.lstsq(a[keep],h[keep],rcond=None)[0]
                predicted=float(coeff[2])
                if np.linalg.norm(coeff[:2])<2 and abs(predicted-self.heights[nearest])<2:result.append(predicted);continue
            result.append(float(self.heights[nearest]))
        return np.asarray(result)


def compile_surfaces(city,samples,ground_height,regularized=False):
    """Build real roof fields plus connected polygon walls; retain measurements."""
    byid={s['id']:s for s in samples};parts=[];audit=[]
    for b in city['buildings']:
        sample=byid[b['id']];absolute=[float(v) if v is not None else float('nan') for v in sample['heights']]
        field=RoofField(sample['points'],np.array(absolute)-ground_height,b['height'])
        poly=make_valid(Polygon(b['outer'],b['holes']));coords=[*b['outer'],*[p for h in b['holes'] for p in h],*sample['points']]
        faces=[];kinds=[]
        for triangle in triangulate(MultiPoint(coords)):
            for clipped in polygons(triangle.intersection(poly)):
                for piece in constrained_delaunay_triangles(clipped).geoms:
                    ring=np.array(piece.exterior.coords)[:3];ys=field.values(ring,regularized)
                    vertices=np.column_stack([ring[:,0],ys,ring[:,1]])
                    if np.cross(vertices[1]-vertices[0],vertices[2]-vertices[0])[1]<0:vertices=vertices[[0,2,1]]
                    faces.append(vertices.tolist());kinds.append('roof')
        # Surface shell boundaries are geometric evidence, not a demand that
        # every thin architectural surface be a separate watertight object.
        for polygon in polygons(poly):
            rings=[polygon.exterior,*polygon.interiors]
            for boundary in rings:
                ring=list(boundary.coords);signed=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]))
                for a,bp in zip(ring,ring[1:]):
                    n=max(1,math.ceil(math.dist(a,bp)/sample['spacing']))
                    nodes=np.linspace(a,bp,n+1);ys=field.values(nodes,regularized)
                    for i in range(n):
                        a0=[nodes[i,0],0,nodes[i,1]];a1=[nodes[i,0],float(ys[i]),nodes[i,1]];b0=[nodes[i+1,0],0,nodes[i+1,1]];b1=[nodes[i+1,0],float(ys[i+1]),nodes[i+1,1]]
                        pair=[[a0,a1,b1],[a0,b1,b0]]
                        if signed<0:pair=[list(reversed(t)) for t in pair]
                        faces.extend(pair);kinds.extend(['wall','wall'])
        parts.append({'id':b['id'],'name':b['name'],'faces':faces,'kinds':kinds})
        audit.append({'id':b['id'],'samples':len(sample['points']),'valid_samples':len(field.points),'roof_range_m':[float(min(field.heights)),float(max(field.heights))] if len(field.heights) else None,'triangles':len(faces)})
    return parts,audit


def ground_surfaces(city,step=6,margin=8):
    all_points=np.array([p for b in city['buildings'] for p in b['outer']]);x0,z0=all_points.min(axis=0)-margin;x1,z1=all_points.max(axis=0)+margin
    occupied=[Polygon(b['outer'],b['holes']) for b in city['buildings']]
    from shapely.ops import unary_union
    ground=box(x0,z0,x1,z1).difference(unary_union(occupied));faces=[]
    for x in np.arange(x0,x1,step):
        for z in np.arange(z0,z1,step):
            clipped=ground.intersection(box(x,z,min(x+step,x1),min(z+step,z1)))
            for piece in polygons(clipped):
                for tri in constrained_delaunay_triangles(piece).geoms:
                    p=np.array(tri.exterior.coords)[:3];v=np.column_stack([p[:,0],np.zeros(3),p[:,1]])
                    if np.cross(v[1]-v[0],v[2]-v[0])[1]<0:v=v[[0,2,1]]
                    faces.append(v.tolist())
    return {'id':'ground','name':'Shared measured appearance ground','faces':faces,'kinds':['ground']*len(faces)},[float(x0),float(z0),float(x1),float(z1)]


def project_points(ecef,camera):
    view=np.asarray(camera['view_matrix']).reshape(4,4,order='F');projection=np.asarray(camera['projection_matrix']).reshape(4,4,order='F')
    p=np.column_stack([ecef,np.ones(len(ecef))]);clip=(projection@view@p.T).T
    w=clip[:,3];ndc=clip[:,:3]/np.where(abs(w[:,None])>1e-12,w[:,None],1)
    uv=np.column_stack([(ndc[:,0]+1)/2,(1-ndc[:,1])/2])
    valid=(w>0)&np.all(uv>.005,axis=1)&(uv[:,0]<.995)&(uv[:,1]<.95)
    return uv,valid


def projection_candidates(parts,frame,camera):
    faces=np.asarray([face for part in parts for face in part['faces']],float)
    centers=faces.mean(axis=1);world=frame.ecef(centers);uv,valid=project_points(world,camera)
    edge1=faces[:,1]-faces[:,0];edge2=faces[:,2]-faces[:,0];normals=np.cross(edge1,edge2);areas=np.linalg.norm(normals,axis=1)/2
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
    local_camera=frame.local_camera(camera);toward=np.asarray(local_camera['position'])-centers;distance=np.linalg.norm(toward,axis=1)
    cosine=np.sum(normals*toward/np.maximum(distance[:,None],1e-9),axis=1)
    vertex_uv,vertex_valid=project_points(frame.ecef(faces.reshape(-1,3)),camera);vertex_uv=vertex_uv.reshape(-1,3,2);vertex_valid=vertex_valid.reshape(-1,3)
    valid&=cosine>.12;valid&=np.all(vertex_valid,axis=1);valid&=areas>1e-6
    score=cosine/np.maximum(distance,1)**2
    return {'faces':faces,'centers':centers,'world':world,'uv':uv,'vertex_uv':vertex_uv,'valid':valid,'score':score,'areas':areas}


def bake_assignments(parts,frame,views,visibility,tolerance=3.5):
    """Choose only front-facing, framed, depth-supported source projections."""
    count=sum(len(p['faces']) for p in parts);best=np.full(count,-1,int);scores=np.full(count,-1.,float);uvs=np.zeros((count,3,2));faces=np.asarray([f for p in parts for f in p['faces']],float)
    for i,view in enumerate(views):
        if view.get('held_out'):continue
        candidate=projection_candidates(parts,frame,view['camera']);hit=np.asarray(visibility[i],float)
        error=np.linalg.norm(hit-candidate['world'],axis=1);good=candidate['valid']&np.isfinite(error)&(error<tolerance)
        choice=good&(candidate['score']>scores)
        best[choice]=i;scores[choice]=candidate['score'][choice];uvs[choice]=candidate['vertex_uv'][choice]
    groups=[];audit=[];offset=0
    for part in parts:
        n=len(part['faces']);chosen=best[offset:offset+n];tri=faces[offset:offset+n];uv=uvs[offset:offset+n]
        for source in sorted(set(chosen)):
            selected=chosen==source
            groups.append({'object_id':part['id'],'kind':'source' if source>=0 else 'fallback','source_view':int(source),'positions':tri[selected].reshape(-1).round(5).tolist(),'uv':np.column_stack([uv[selected].reshape(-1,2)[:,0],1-uv[selected].reshape(-1,2)[:,1]]).reshape(-1).round(7).tolist() if source>=0 else []})
        area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
        total=float(sum(area));covered=float(sum(area[chosen>=0]));audit.append({'id':part['id'],'triangles':n,'projected_area_coverage':covered/total if total else 0,'uncovered_triangles':int(sum(chosen<0))})
        offset+=n
    return groups,audit
