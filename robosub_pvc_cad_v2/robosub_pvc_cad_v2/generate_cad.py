"""RoboSub PVC frame V2. Run: python generate_cad.py. Units mm."""
import cadquery as cq, math, os, csv
from cadquery import exporters
OUT=os.path.dirname(os.path.abspath(__file__))
PVC=21.34; FIT=0.65; BORE=PVC+FIT; SOCKET_OD=BORE+10
R=250/math.sqrt(3); Z=30

def cyl(r,h,p,axis):return cq.Solid.makeCylinder(r,h,cq.Vector(*p),cq.Vector(*axis))
def ring_socket(start,axis,length,depth=None):
    # tube closed at far end, opening at start
    outer=cyl(SOCKET_OD/2,length,start,axis)
    inner=cyl(BORE/2,depth or length-4,start,axis)
    return outer.cut(inner)

def hub():
    s=cq.Workplane('XY').sphere(43/2).val().translate((0,0,Z))
    for a in (0,120,240):
        d=(math.cos(math.radians(a)),math.sin(math.radians(a)),0)
        # opening at radius 40, towards center; solid outer 12..40
        p=tuple(40*x for x in d[:2])+(Z,)
        neg=(-d[0],-d[1],0)
        s=s.fuse(cyl(SOCKET_OD/2,28,tuple(12*x for x in d[:2])+(Z,),d))
        s=s.cut(cyl(BORE/2,25,p,neg))
    # down-facing mast opening z=-10, depth 28
    s=s.fuse(cyl(SOCKET_OD/2,35,(0,0,-10),(0,0,1)))
    s=s.cut(cyl(BORE/2,28,(0,0,-10),(0,0,1)))
    return s

def upper_mount():
    # local X radial axis, hydrophone center at x=R, acoustic tip at z=0.
    # pipe socket opens at x=110, 25 mm depth towards +x
    s=ring_socket((110,0,Z),(1,0,0),29,25)
    # vertical open guide around rigid upper hydrophone region at z=30
    # opening ID 14.8mm accommodates a ~1mm compliant liner, verify on actual sensor
    guide=cyl(13.5,16,(R,0,22),(0,0,1)).cut(cyl(7.4,18,(R,0,21),(0,0,1)))
    # remove front ~90-degree sector: guide, not a squeezing clamp
    notch=cq.Workplane('XY').box(20,17,22).val().translate((R+9,0,30))
    guide=guide.cut(notch)
    bridge=cq.Workplane('XY').box(22,15,16).val().translate(((R+132)/2,0,30))
    s=s.fuse(bridge).fuse(guide)
    # cable tie passages through guide shoulders, away from hydrophone sensing tip
    for y in (-10,10):
        s=s.cut(cq.Workplane('XY').box(4,3.4,10).val().translate((R-6,y,30)))
    return s

def lower_mount():
    # Bottom hydrophone lies HORIZONTALLY, acoustic tip at (0,0,-400).
    # This avoids the sensor body intersecting the downward PVC mast.
    s=ring_socket((0,0,-340),(0,0,-1),29,25)
    guide=cyl(13.5,16,(22,0,-400),(1,0,0)).cut(cyl(7.4,18,(21,0,-400),(1,0,0)))
    guide=guide.cut(cq.Workplane('XY').box(20,20,18).val().translate((30,0,-389)))
    # angled web from the mast fitting to the upper side of the horizontal guide
    p1=cq.Vector(0,0,-363);p2=cq.Vector(29,0,-388)
    direction=p2-p1
    web=cyl(8,direction.Length,p1.toTuple(),direction.normalized().toTuple())
    return s.fuse(web).fuse(guide)

def fit_coupon():
    return ring_socket((0,0,0),(0,0,1),18,14)

def cable_clip():
    s=cyl(16,10,(0,0,0),(0,0,1)).cut(cyl((BORE+0.8)/2,12,(0,0,-1),(0,0,1)))
    s=s.cut(cq.Workplane('XY').box(18,5,12).val().translate((16,0,5)))
    tab=cq.Workplane('XY').box(13,10,10).val().translate((-17,0,5))
    s=s.fuse(tab)
    s=s.cut(cyl(2.6,12,(-18,0,-1),(0,0,1)))
    return s

def dummy():
    # 12 mm diameter gauge only, NOT a complete manufacturer-accurate S1f body
    return cyl(6,55,(0,0,0),(0,0,1))

parts={'central_hub':hub(),'upper_hydrophone_mount':upper_mount(),'lower_hydrophone_mount':lower_mount(),'pvc_socket_fit_coupon':fit_coupon(),'cable_clip':cable_clip(),'sensor_12mm_fit_gauge':dummy()}
for name,shape in parts.items():
    exporters.export(shape,os.path.join(OUT,name+'.stl'),tolerance=0.08,angularTolerance=0.15)
    exporters.export(shape,os.path.join(OUT,name+'.step'))

# Assembly placement; solids only, pipes as full cylinder visual aids (not hollow)
shapes=[parts['central_hub']]
for angle in (0,120,240):
    m=parts['upper_hydrophone_mount'].rotate((0,0,0),(0,0,1),angle)
    shapes.append(m)
    d=(math.cos(math.radians(angle)),math.sin(math.radians(angle)),0)
    shapes.append(cyl(PVC/2,120,(15*d[0],15*d[1],Z),d))
    # acoustic center marker at each vertex z=0
    shapes.append(cyl(6,55,(R*d[0],R*d[1],0),(0,0,1)))
shapes.append(parts['lower_hydrophone_mount'])
shapes.append(cyl(PVC/2,358,(0,0,-365),(0,0,1))) # from -365 to -7, 358mm
shapes.append(cyl(6,55,(0,0,-400),(1,0,0)))
assembly=cq.Compound.makeCompound(shapes)
exporters.export(assembly,os.path.join(OUT,'full_frame_assembly.step'))
exporters.export(assembly,os.path.join(OUT,'full_frame_assembly.stl'),tolerance=0.12)
with open(os.path.join(OUT,'pipe_cut_list.csv'),'w',newline='') as f:
    w=csv.writer(f);w.writerow(['item','quantity','length_mm','notes']);w.writerow(['radial_arm',3,120,'25mm nominal insertion each end; dry-fit and adjust']);w.writerow(['vertical_mast',1,380,'bottom socket nominal insertion 25mm; top hub insertion ~27mm'])
print('Created CAD files in',OUT)
