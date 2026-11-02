"""Render coordinate-safe repository figures from reviewed aggregate or synthetic data."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,Rectangle,Ellipse
from demo import build_fixture
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/figures'
BLUE='#235789';GOLD='#b57912';GREY='#66717c';INK='#142b3c';LIGHT='#e9eff3'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,
'axes.spines.right':False,'axes.labelcolor':INK,'text.color':INK,'axes.titleweight':'bold',
'figure.facecolor':'white','savefig.facecolor':'white','svg.hashsalt':'geoarb'})

def save(fig,name):
    OUT.mkdir(parents=True,exist_ok=True)
    fig.savefig(OUT/f'{name}.png',dpi=170,bbox_inches='tight',metadata={'Software':'GeoArb figure renderer'})
    fig.savefig(OUT/f'{name}.svg',bbox_inches='tight',metadata={'Date':None})
    svg=OUT/f'{name}.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)

def main():
    fig,ax=plt.subplots(figsize=(12,4.2));ax.set(xlim=(0,12),ylim=(0,4));ax.axis('off')
    boxes=[('Acquire & attribute','GTK geology • Tukes rights\nExternal, versioned inputs'),
           ('Build spatial features','Metric CRS • cell overlays\nFaults • contacts • gravity'),
           ('Evaluate honestly','Whole-block holdouts\nTraining-only preprocessing'),
           ('Measure sensitivity','Baselines & ablations\nMonte Carlo rank stability')]
    for i,(title,body) in enumerate(boxes):
        x=.22+i*3
        ax.add_patch(FancyBboxPatch((x,1.4),2.52,1.5,boxstyle='round,pad=.12',facecolor=LIGHT,edgecolor=BLUE,lw=1.3))
        ax.text(x+1.26,2.55,title,ha='center',fontsize=11,weight='bold')
        ax.text(x+1.26,1.95,body,ha='center',va='center',fontsize=10,linespacing=1.6)
        if i<3:ax.annotate('',(x+2.95,2.15),(x+2.75,2.15),arrowprops={'arrowstyle':'->','color':BLUE,'lw':1.5})
    ax.text(.1,3.55,'GeoArb Finland | research pipeline',fontsize=18,weight='bold')
    ax.text(.1,.55,'Offline demo: synthetic inputs exercise the same core functions. No mineral discovery is inferred.',fontsize=11)
    save(fig,'pipeline')
    # Natural Earth is the only third-party geometry in the release.
    g=gpd.read_file(ROOT/'data/context/northern_europe.geojson')
    fig,ax=plt.subplots(figsize=(7,7))
    g.plot(ax=ax,color=LIGHT,edgecolor='white',linewidth=.8)
    g[g.ADM0_A3=='FIN'].plot(ax=ax,color='#d0dee8',edgecolor=BLUE,linewidth=.9)
    ax.add_patch(Ellipse((25.2,67.7),4.,1.25,facecolor=GOLD,edgecolor=GOLD,alpha=.35))
    ax.annotate('Central Lapland\ngeneral study region',xy=(25.2,67.7),xytext=(29.6,69.2),fontsize=11,
                arrowprops={'arrowstyle':'-','color':INK})
    ax.text(25,63.8,'FINLAND',ha='center',fontsize=13,weight='bold')
    ax.set(xlim=(18,33.5),ylim=(59,71),xlabel='Longitude (°E)',ylabel='Latitude (°N)')
    ax.set_aspect(1/np.cos(np.deg2rad(65)))
    ax.set_title('Finland and the study region',loc='left',pad=18)
    fig.text(.12,.01,'Made with Natural Earth (public domain), simplified.\nShaded ellipse is an illustrative region, not the belt boundary or a target.',fontsize=9)
    save(fig,'study_region')
    f,grid,lines,bed=build_fixture()
    fig,axes=plt.subplots(1,2,figsize=(12,5.2))
    for ax in axes:
        for line in lines.geometry:
            x,y=line.xy;ax.plot(np.array(x)/1000,np.array(y)/1000,color=INK,lw=1.2)
        ax.axvline(24,color=GOLD,ls='--',lw=1.4)
        ax.set(xlabel='Fictional eastings (km)',ylabel='Fictional northings (km)',xlim=(0,60),ylim=(0,60));ax.set_aspect('equal')
    for ax,col,title in zip(axes,['dist_major_shear','gravity_gradient'],['Distance to synthetic faults (km)','Synthetic gravity-gradient feature (unitless)']):
        values=f[col]/1000 if col=='dist_major_shear' else f[col]
        im=ax.imshow(values.to_numpy().reshape(30,30),origin='lower',extent=(0,60,0,60),cmap='cividis',alpha=.8)
        ax.set_title(title,fontsize=11,loc='left');fig.colorbar(im,ax=ax,fraction=.046,pad=.04)
    fig.suptitle('Feature engineering | SYNTHETIC DEMONSTRATION',fontsize=16,weight='bold')
    fig.text(.08,.01,'Solid lines: invented faults. Dashed line: invented contact. No Finnish measurements or target coordinates.',fontsize=10)
    fig.tight_layout(rect=(0,.06,1,.92));save(fig,'feature_layers')
    v=json.loads((ROOT/'data/historical/STEP2_VALIDATION.json').read_text())
    names=['model_xgb_oof','baseline_distfault','baseline_random'];labels=['XGBoost','Fault distance','Random (one seed)'];colors=[BLUE,GOLD,GREY]
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for ax,key,title in [(axes[0],'roc_auc','ROC-AUC'),(axes[1],'capture','Known positives in top 5% of cells')]:
        vals=[v[key][n] if key=='roc_auc' else v[key][n]['top5pct']*8 for n in names]
        ax.barh(labels,vals,color=colors,height=.55)
        for i,val in enumerate(vals):ax.text(val+.025 if key=='roc_auc' else val+.15,i,f'{val:.3f}' if key=='roc_auc' else f'{int(val)} / 8',va='center',fontsize=11)
        ax.invert_yaxis();ax.set_xlim(0,1.08 if key=='roc_auc' else 8.5);ax.set_title(title,fontsize=12,loc='left')
        ax.set_xticks([0,.5,1] if key=='roc_auc' else [0,2,4,6,8])
        if key=='roc_auc':ax.axvline(.5,color=GREY,lw=1,ls=':')
    fig.suptitle('Historical reported performance | 3,649 cells, 8 positives',fontsize=16,weight='bold')
    fig.text(.07,.015,'Saved summaries agree; predictions and training inputs are absent. Metrics were NOT independently reproduced.\nAUC improvement does not establish practical discovery skill. Historical preprocessing leakage remains unresolved.',fontsize=9)
    fig.tight_layout(rect=(0,.13,1,.92));save(fig,'historical_performance')
    mc=pd.read_csv(ROOT/'data/example/synthetic_mc.csv').head(8).iloc[::-1]
    fig,axes=plt.subplots(1,2,figsize=(11,5.6))
    labels=[x.replace('synthetic_','S') for x in mc.cell_id]
    axes[0].errorbar(mc.mc_score_mean,labels,xerr=mc.mc_score_sd,fmt='o',color=BLUE,ecolor=GREY,capsize=3)
    axes[0].set(xlabel='Heuristic score: mean ± simulation SD',xlim=(0,max(mc.mc_score_mean+mc.mc_score_sd)*1.15))
    axes[1].barh(labels,mc.top_5_freq,color=BLUE,height=.55)
    axes[1].set(xlim=(0,1),xlabel='Frequency in top 5 cells (0–1)')
    fig.suptitle('Monte Carlo ranking sensitivity | SYNTHETIC',fontsize=16,weight='bold')
    fig.text(.08,.015,'500 perturbations • 16 synthetic candidates • seed 42. SD is scenario spread, not a confidence interval.\nTop-5 frequency is conditional on this pool and chosen assumptions; it is not a mineral-discovery probability.',fontsize=9)
    fig.tight_layout(rect=(0,.1,1,.93));save(fig,'monte_carlo')
    folds=json.loads((ROOT/'data/example/folds.json').read_text());hold=set(folds[0]['test_groups'])
    fig,ax=plt.subplots(figsize=(8,6))
    for bx in range(3):
        for by in range(3):
            test=f'{bx}_{by}' in hold
            ax.add_patch(Rectangle((bx*20,by*20),20,20,facecolor=GOLD if test else LIGHT,edgecolor=INK,lw=1.1,hatch='//' if test else None))
            ax.text(bx*20+10,by*20+10,'TEST' if test else 'TRAIN',ha='center',va='center',fontsize=11,weight='bold')
    ax.set(xlim=(0,60),ylim=(0,60),xlabel='Fictional eastings (km)',ylabel='Fictional northings (km)',xticks=[0,20,40,60],yticks=[0,20,40,60]);ax.set_aspect('equal')
    ax.set_title('Spatial cross-validation | one synthetic fold',loc='left',fontsize=15,pad=15)
    fig.text(.10,.01,'Entire 20 km blocks are held out. Imputation and class weights use training data only.\nNo train/test block overlap; adjacent boundaries can still share spatial dependence.',fontsize=9)
    fig.subplots_adjust(bottom=.22)
    save(fig,'spatial_cv')

if __name__=='__main__':main()
