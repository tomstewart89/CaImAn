# -*- coding: utf-8 -*-
"""
Created on Wed Feb 24 18:39:45 2016

@author: Andrea Giovannucci

For explanation consult at https://github.com/agiovann/Constrained_NMF/releases/download/v0.4-alpha/Patch_demo.zip
and https://github.com/agiovann/Constrained_NMF

"""
from __future__ import division
from __future__ import print_function
#%%
from builtins import str
from builtins import range
from past.utils import old_div
try:
    if __IPYTHON__:
        # this is used for debugging purposes only. allows to reload classes when changed
        get_ipython().magic('load_ext autoreload')
        get_ipython().magic('autoreload 2')
except:
    print('NOT IPYTHON')

import matplotlib as mpl
mpl.use('TKAgg')
from matplotlib import pyplot as plt
#plt.ion()

import sys
import numpy as np
import ca_source_extraction as cse

#sys.path.append('../SPGL1_python_port')
#%
from time import time
from scipy.sparse import coo_matrix
import pylab as pl
import glob
import os
import scipy
from ipyparallel import Client
import calblitz as cb
#%% download example
import urllib.request, urllib.parse, urllib.error
import shutil

if not os.path.exists('PPC.tif'):
    url = "https://www.dropbox.com/s/z8rj5dekrl6yxfr/PPC.tif?dl=1"  # dl=1 is important
    u = urllib.request.urlretrieve(url)
    shutil.move(u[0],'./PPC.tif')

#%% load and motion correct movie
m=cb.load('PPC.tif',fr=30)    
m -= np.min(m)
play_movie = False

if play_movie:
    m.play(backend='opencv',magnification=2,fr=60,gain=5.)
#%%
max_w=25 # max pixel shift in width direction
max_h=25
mc,shifts,corrs, template = m.motion_correct(max_shift_w=max_w,max_shift_h=max_h,remove_blanks=True)

if play_movie:
    mc.play(backend='opencv',magnification=2,fr=60,gain=5.)
#%%
mc.save('PPC_mc.tif')
fnames=['PPC_mc.tif']

#%% start cluster for efficient computation
single_thread=False
backend='local'
if single_thread:
    dview=None
else:    
    try:
        c.close()
    except:
        print('C was not existing, creating one')
    print("Stopping  cluster to avoid unnencessary use of memory....")
    sys.stdout.flush()  
    if backend == 'SLURM':
        try:
            cse.utilities.stop_server(is_slurm=True)
        except:
            print('Nothing to stop')
        slurm_script='/mnt/xfs1/home/agiovann/SOFTWARE/Constrained_NMF/SLURM/slurmStart.sh'
        cse.utilities.start_server(slurm_script=slurm_script)
        pdir, profile = os.environ['IPPPDIR'], os.environ['IPPPROFILE']
        c = Client(ipython_dir=pdir, profile=profile)        
    else:
        cse.utilities.stop_server()
        cse.utilities.start_server()        
        c=Client()
    n_processes=len(c)
    print(('Using '+ str(len(c)) + ' processes'))
    dview=c[:len(c)]

#%%
downsample_factor=.5 # use .2 or .1 if file is large and you want a quick answer
idx_xy=None
base_name='Yr'
name_new=cse.utilities.save_memmap_each(fnames, dview=dview,base_name=base_name, resize_fact=(1, 1, downsample_factor), remove_init=0,idx_xy=idx_xy )
name_new.sort(key=lambda fn: np.int(fn[len(base_name):fn.find('_')]))
print(name_new)
#%%
n_chunks=6 # increase this number if you have memory issues at this point
fname_new=cse.utilities.save_memmap_join(name_new,base_name='Yr', n_chunks=6, dview=dview)
#%%
#fname_new='Yr_d1_501_d2_398_d3_1_order_F_frames_369_.mmap'
Yr,dims,T=cse.utilities.load_memmap(fname_new)
d1,d2=dims
Y=np.reshape(Yr,dims+(T,),order='F')
#%%
Cn = cse.utilities.local_correlations(Y[:,:,:3000])
pl.imshow(Cn,cmap='gray')  

#%%
rf=10 # half-size of the patches in pixels. rf=25, patches are 50x50
stride = 2 #amounpl.it of overlap between the patches in pixels    
K=6 # number of neurons expected per patch
gSig=[4,4] # expected half size of neurons
merge_thresh=0.8 # merging threshold, max correlation allowed
p=2 #order of the autoregressive system
memory_fact=1; #unitless number accounting how much memory should be used. You will need to try different values to see which one would work the default is OK for a 16 GB system
save_results=False
#%% RUN ALGORITHM ON PATCHES
options_patch = cse.utilities.CNMFSetParms(Y,n_processes,p=0,gSig=gSig,K=K,ssub=1,tsub=4,thr=merge_thresh)
A_tot,C_tot,YrA_tot,b,f,sn_tot, optional_outputs = cse.map_reduce.run_CNMF_patches(fname_new, (d1, d2, T), options_patch,rf=rf,stride = stride,
                                                                        dview=dview,memory_fact=memory_fact)
print(('Number of components:' + str(A_tot.shape[-1])))      
#%%
if save_results:
    np.savez('results_analysis_patch.npz',A_tot=A_tot.todense(), C_tot=C_tot, sn_tot=sn_tot,d1=d1,d2=d2,b=b,f=f)    
#%% if you have many components this might take long!
if False:
    pl.figure()
    crd = cse.utilities.plot_contours(A_tot,Cn,thr=0.9)
#%% set parameters for full field of view analysis
options = cse.utilities.CNMFSetParms(Y,n_processes,p=0,gSig=gSig,K=A_tot.shape[-1],thr=merge_thresh)
pix_proc=np.minimum(np.int((d1*d2)/n_processes/(old_div(T,2000.))),np.int(old_div((d1*d2),n_processes))) # regulates the amount of memory used
options['spatial_params']['n_pixels_per_process']=pix_proc
options['temporal_params']['n_pixels_per_process']=pix_proc
#%% merge spatially overlaping and temporally correlated components      
A_m,C_m,nr_m,merged_ROIs,S_m,bl_m,c1_m,sn_m,g_m=cse.merge_components(Yr,A_tot,[],np.array(C_tot),[],np.array(C_tot),[],options['temporal_params'],options['spatial_params'],dview=dview,thr=options['merging']['thr'],mx=np.Inf)     
#%% update temporal to get Y_r
options['temporal_params']['p']=0
options['temporal_params']['fudge_factor']=0.96 #change ifdenoised traces time constant is wrong
options['temporal_params']['backend']='ipyparallel'
C_m,f_m,S_m,bl_m,c1_m,neurons_sn_m,g2_m,YrA_m = cse.temporal.update_temporal_components(Yr,A_m,b,C_m,f,dview=dview,bl=None,c1=None,sn=None,g=None,**options['temporal_params'])

#%% get rid of evenrually noisy components. 
# But check by visual inspection to have a feeling fot the threshold. Try to be loose, you will be able to get rid of more of them later!
final_frate = 30
tB = np.minimum(-2,np.floor(-5./30*final_frate))
tA = np.maximum(5,np.ceil(25./30*final_frate))
Npeaks=10
traces=C_m+YrA_m
#        traces_a=traces-scipy.ndimage.percentile_filter(traces,8,size=[1,np.shape(traces)[-1]/5])
#        traces_b=np.diff(traces,axis=1)
fitness_raw, fitness_delta, erfc_raw, erfc_delta, r_values, significant_samples =\
             cse.utilities.evaluate_components(Y, traces, A_m, C_m, b, f_m, \
             remove_baseline=True, N=5, robust_std=False, Athresh = 0.1, Npeaks = Npeaks, tB=tB, tA = tA, thresh_C = 0.3)

idx_components_r=np.where(r_values>=.5)[0]
idx_components_raw=np.where(fitness_raw<-20)[0]        
idx_components_delta=np.where(fitness_delta<-10)[0]   


idx_components=np.union1d(idx_components_r,idx_components_raw)
idx_components=np.union1d(idx_components,idx_components_delta)  
idx_components_bad=np.setdiff1d(list(range(len(traces))),idx_components)

print(' ***** ')
print((len(traces)))
print((len(idx_components)))
#%%
A_m=A_m[:,idx_components]
C_m=C_m[idx_components,:]   

#%% display components  DO NOT RUN IF YOU HAVE TOO MANY COMPONENTS
pl.figure()
crd = cse.utilities.plot_contours(A_m,Cn,thr=0.9)
#%%
print(('Number of components:' + str(A_m.shape[-1])))  
#%% UPDATE SPATIAL COMPONENTS
t1 = time()
A2,b2,C2 = cse.spatial.update_spatial_components(Yr, C_m, f, A_m, sn=sn_tot,dview=dview, **options['spatial_params'])
print((time() - t1))
#%% UPDATE TEMPORAL COMPONENTS
options['temporal_params']['p']=p
options['temporal_params']['fudge_factor']=0.96 #change ifdenoised traces time constant is wrong
C2,f2,S2,bl2,c12,neurons_sn2,g21,YrA = cse.temporal.update_temporal_components(Yr,A2,b2,C2,f,dview=dview, bl=None,c1=None,sn=None,g=None,**options['temporal_params'])
#%% Order components
#A_or, C_or, srt = cse.utilities.order_components(A2,C2)
#%% stop server and remove log files
cse.utilities.stop_server(is_slurm = (backend == 'SLURM')) 
log_files=glob.glob('Yr*_LOG_*')
for log_file in log_files:
    os.remove(log_file)
#%% order components according to a quality threshold and only select the ones wiht quality larger than quality_threshold. 
B = np.minimum(-2,np.floor(-5./30*final_frate))
tA = np.maximum(5,np.ceil(25./30*final_frate))
Npeaks=10
traces=C2+YrA
#        traces_a=traces-scipy.ndimage.percentile_filter(traces,8,size=[1,np.shape(traces)[-1]/5])
#        traces_b=np.diff(traces,axis=1)
fitness_raw, fitness_delta, erfc_raw, erfc_delta, r_values, significant_samples = cse.utilities.evaluate_components(Y, traces, A2, C2, b2, f2, remove_baseline=True, N=5, robust_std=False, Athresh = 0.1, Npeaks = Npeaks, tB=tB, tA = tA, thresh_C = 0.3)

idx_components_r=np.where(r_values>=.6)[0]
idx_components_raw=np.where(fitness_raw<-60)[0]        
idx_components_delta=np.where(fitness_delta<-20)[0]   


min_radius=gSig[0]-2
masks_ws,idx_blobs,idx_non_blobs=cse.utilities.extract_binary_masks_blob(
A2.tocsc(), min_radius, dims, num_std_threshold=1, 
minCircularity= 0.6, minInertiaRatio = 0.2,minConvexity =.8)




idx_components=np.union1d(idx_components_r,idx_components_raw)
idx_components=np.union1d(idx_components,idx_components_delta)  
idx_blobs=np.intersect1d(idx_components,idx_blobs)   
idx_components_bad=np.setdiff1d(list(range(len(traces))),idx_components)

print(' ***** ')
print((len(traces)))
print((len(idx_components)))
print((len(idx_blobs)))
#%% visualize components
pl.figure();
pl.subplot(1,3,1)
crd = cse.utilities.plot_contours(A2.tocsc()[:,idx_components],Cn,thr=0.9)
pl.subplot(1,3,2)
crd = cse.utilities.plot_contours(A2.tocsc()[:,idx_blobs],Cn,thr=0.9)
pl.subplot(1,3,3)
crd = cse.utilities.plot_contours(A2.tocsc()[:,idx_components_bad],Cn,thr=0.9)
#%%
cse.utilities.view_patches_bar(Yr,scipy.sparse.coo_matrix(A2.tocsc()[:,idx_components]),C2[idx_components,:],b2,f2, dims[0],dims[1], YrA=YrA[idx_components,:],img=Cn)  
#%%
cse.utilities.view_patches_bar(Yr,scipy.sparse.coo_matrix(A2.tocsc()[:,idx_components_bad]),C2[idx_components_bad,:],b2,f2, dims[0],dims[1], YrA=YrA[idx_components_bad,:],img=Cn)  
#%% STOP CLUSTER
pl.close()
if not single_thread:    
    c.close()
    cse.utilities.stop_server()
#%% save analysis results in python and matlab format
if save_results:
    np.savez('results_analysis.npz',Cn=Cn,A_tot=A_tot.todense(), C_tot=C_tot, sn_tot=sn_tot, A2=A2.todense(),C2=C2,b2=b2,S2=S2,f2=f2,bl2=bl2,c12=c12, neurons_sn2=neurons_sn2, g21=g21,YrA=YrA,d1=d1,d2=d2,idx_components=idx_components, fitness=fitness, erfc=erfc)    
    scipy.io.savemat('output_analysis_matlab.mat',{'A2':A2,'C2':C2 , 'YrA':YrA, 'S2': S2 ,'YrA': YrA, 'd1':d1,'d2':d2,'idx_components':idx_components, 'fitness':fitness })
#%% 


#%% RELOAD COMPONENTS!
#load_results=True
#if load_results:
#    import sys
#    import numpy as np
#    import ca_source_extraction as cse
#    from scipy.sparse import coo_matrix
#    import scipy
#    import pylab as pl
#    import calblitz as cb
#    
#    
#    
#    with np.load('results_analysis.npz')  as ld:
#          locals().update(ld)
#    
#    fname_new=glob.glob('Yr0*_.mmap')[0]
#    
#    Yr,(d1,d2),T=cse.utilities.load_memmap(fname_new)
#    d,T=np.shape(Yr)
#    Y=np.reshape(Yr,(d1,d2,T),order='F') # 3D version of the movie
#    
#    dims=(d1,d2)
#    traces=C2+YrA
#    idx_components, fitness, erfc,r_values,num_significant_samples = cse.utilities.evaluate_components(traces,N=5,robust_std=False)
#    #cse.utilities.view_patches(Yr,coo_matrix(A_or),C_or,b2,f2,d1,d2,YrA = YrA[srt,:], secs=1)
#    cse.utilities.view_patches_bar(Yr,scipy.sparse.coo_matrix(A2[:,idx_components]),C2[idx_components,:],b2,f2, d1,d2, YrA=YrA[idx_components,:])  
##%% only select blob-like structures
#min_radius=3
#masks_ws,pos_examples,neg_examples=cse.utilities.extract_binary_masks_blob(
#scipy.sparse.coo_matrix(A2).tocsc()[:,:], min_radius, dims, num_std_threshold=1, 
#minCircularity= 0.5, minInertiaRatio = 0.2,minConvexity = .8)
#np.savez(os.path.join(os.path.split(fname_new)[0],'regions_CNMF.npz'),masks_ws=masks_ws,pos_examples=pos_examples,neg_examples=neg_examples)
##%% visualize them
#pl.subplot(1,2,1)
#final_masks=np.array(masks_ws)[pos_examples]
#pl.imshow(np.reshape(final_masks.max(0),dims,order='F'),vmax=1)
#pl.title('Positive examples')
#pl.subplot(1,2,2)
#neg_examples_masks=np.array(masks_ws)[neg_examples]
#pl.imshow(np.reshape(neg_examples_masks.max(0),dims,order='F'),vmax=1)
#pl.title('Negative examples')
##%% visualize them again
#cse.utilities.view_patches_bar(Yr,scipy.sparse.coo_matrix(A2.tocsc()[:,pos_examples]),C2[pos_examples,:],b2,f2, d1,d2, YrA=YrA[pos_examples,:])  
