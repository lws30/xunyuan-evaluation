"""Draw the five maps from the actual scoring geometry."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

root=Path(__file__).resolve().parents[1]/'challenges/v2'
reference=json.loads((root/'reference.json').read_text())
for route in reference['routes']:
    fig,ax=plt.subplots(figsize=(9,7),layout='constrained')
    step=route['cell_size_m'];cells=route['driveable_cells']
    polygons=[[(x*step,y*step),((x+1)*step,y*step),((x+1)*step,(y+1)*step),(x*step,(y+1)*step)] for x,y in cells]
    ax.add_collection(PolyCollection(polygons,facecolors='#dce3e8',edgecolors='none'))
    path=route['path_xy'][:len(route['path_xy'])//2+1]
    ax.plot([p[0] for p in path],[p[1] for p in path],color='#2465b4',lw=2,zorder=2)
    for a,b in zip(path,path[1:]):
        ax.annotate('',xy=(a[0]+.7*(b[0]-a[0]),a[1]+.7*(b[1]-a[1])),xytext=(a[0]+.4*(b[0]-a[0]),a[1]+.4*(b[1]-a[1])),
                    arrowprops={'arrowstyle':'->','color':'#2465b4','lw':1.5})
    for i,j in enumerate(route['junctions']):
        x,y=j['center_xy'];ax.scatter([x],[y],s=25,color='#2465b4',zorder=3)
        ax.annotate(f"{j['id']} ({j['kind']}) {j['turn']}",(x,y),xytext=(10,12 if i%2==0 else -20),textcoords='offset points',
                    fontsize=9,bbox={'facecolor':'white','alpha':.85,'edgecolor':'none'})
    for text,p,color in [('START / RETURN',path[0],'#258038'),('TURN AROUND',path[-1],'#b57500')]:
        ax.scatter([p[0]],[p[1]],s=55,color=color,zorder=3)
        ax.annotate(text,p,xytext=(8,-18),textcoords='offset points',fontsize=9,color=color)
    ax.set_aspect('equal');ax.autoscale_view();ax.margins(.12);ax.set_xlabel('x (m)');ax.set_ylabel('y (m)')
    ax.set_title(route['id']+' | Five junctions, then return along the route')
    ax.spines[['top','right']].set_visible(False)
    fig.savefig(root/'maps'/f"{route['id']}.png",dpi=130);plt.close(fig)
print('Drew five map previews.')
