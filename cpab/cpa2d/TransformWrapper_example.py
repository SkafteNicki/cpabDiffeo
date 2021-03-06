#!/usr/bin/env python
"""
Created on Mon Sep 29 09:46:24 2014

Author: Oren Freifeld
Email: freifeld@csail.mit.edu
"""


import numpy as np
import pylab 
from pylab import plt
from of.utils import *
import of.plt
from of.gpu import CpuGpuArray
from pyimg import *
from cpab.cpa2d.TransformWrapper import TransformWrapper
       
from of.gpu import GpuTimer

plt.close('all')
if not inside_spyder():
     pylab.ion()
     
def example(img=None,tess='I',eval_cell_idx=True,eval_v=True,show_downsampled_pts=True,
            valid_outside=True,base=[1,1],
            scale_spatial=.1,
            scale_value=100,
            permute_cell_idx_for_display=True,
            nLevels=3,
            vol_preserve=False,
            zero_v_across_bdry=[0,0],
            use_lims_when_plotting=True):
          
    show_downsampled_pts = bool(show_downsampled_pts)
    eval_cell_idx = bool(eval_cell_idx)
    eval_v = bool(eval_cell_idx)
    valid_outside = bool(valid_outside)
    permute_cell_idx_for_display = bool(permute_cell_idx_for_display)
    vol_preserve = bool(vol_preserve)
    
    if img is None:
        img =  Img(get_std_test_img())
    else:
        img=Img(img)
        img = img[:,:,::-1] # bgr2rgb
        
        
    
    tw = TransformWrapper(nRows=img.shape[0],
                          nCols=img.shape[1],
                          nLevels=nLevels,  
                          base=base,
                          scale_spatial=scale_spatial, # controls the prior's smoothness
                          scale_value=scale_value, # controls the prior's variance
                          tess=tess,
                          vol_preserve=vol_preserve,
                          zero_v_across_bdry=zero_v_across_bdry,
                          valid_outside=valid_outside)
    print tw
         
     
    # You probably want to do that: padding image border with zeros
    border_width=1
    img[:border_width]=0
    img[-border_width:]=0
    img[:,:border_width]=0
    img[:,-border_width:]=0      
    
    # The tw.calc_T_fwd (or tw.calc_T_inv) is always done in gpu.
    # After using it to compute new pts, 
    # you may want to use remap (to warp an image accordingly). 
    # If you will use tw.remap_fwd (or tw.remap_inv), which is done in gpu,
    # then the image type can be either float32 or float64.
    # But if you plan to use tw.tw.remap_fwd_opencv (or tw.remap_inv_opencv),
    # which is done in cpu (hence slightly lower) but supports better 
    # interpolation methods, then the image type must be np.float32.
    
#    img_original = CpuGpuArray(img.copy().astype(np.float32))
    img_original = CpuGpuArray(img.copy().astype(np.float64))
    
    img_wrapped_fwd= CpuGpuArray.zeros_like(img_original)
    img_wrapped_bwd= CpuGpuArray.zeros_like(img_original)
    
     
    seed=0
    np.random.seed(seed)    
               
    ms_Avees=tw.get_zeros_PA_all_levels()
    ms_theta=tw.get_zeros_theta_all_levels() 
    
    for level in range(tw.ms.nLevels):  
        if level==0:
            tw.sample_gaussian(level,ms_Avees[level],ms_theta[level],mu=None)# zero mean
        else:
            tw.sample_from_the_ms_prior_coarse2fine_one_level(ms_Avees,ms_theta,
                                                                level_fine=level)                
    
    
    print('\nimg shape: {}\n'.format(img_original.shape))

    # You don't have use these. You can use any 2d array 
    # that has two columns (regardless of the number of rows).
    pts_src = tw.pts_src_dense
    
    # Create buffers for the output
    pts_fwd = CpuGpuArray.zeros_like(pts_src) 
    pts_inv = CpuGpuArray.zeros_like(pts_src)  

   
    for level in range(tw.ms.nLevels):
        
        
        #######################################################################
        # instead of the tw.sample_from_the_ms_prior() above,
        # you may want to use one of the following.        
        # 1)
        # tw.sample_gaussian(level,ms_Avees[level],ms_theta[level],mu=None)# zero mean
        # 2)
        # tw.sample_gaussian(level,ms_Avees[level],ms_theta[level],mu=some_user_specified_mu)
        # The following should be used only for level>0 :
        # 3)
        # tw.sample_normal_in_one_level_using_the_coarser_as_mean(Avees_coarse=ms_Avees[level-1], 
        #                                                        Avees_fine=ms_Avees[level],
        #                                                        theta_fine=ms_theta[level], 
        #                                                        level_fine=level)
        #
        #######################################################################
        
        
#        You can also change the values this way:
#         cpa_space = tw.ms.L_cpa_space[level]
#        theta = cpa_space.get_zeros_theta()
#        theta[:] = some values
#        Avees = cpa_space.get_zeros_PA()
#        cpa_space.theta2Avees(theta,Avees)
#        cpa_space.update_pat(Avees)         
              
        
        # This step is important and must be done 
        # before are trying to "use" the new values of 
        # the (vectorized) A's. 
        tw.update_pat_from_Avees(ms_Avees[level],level) 
        
     
        if eval_v:
            # Evaluating the velocity field. 
            # You don't have to do it in unless you want to visualize v.
            # (when evaluting the treansformation, v will be internally 
            # evaluated anyway -- but its result won't be stored)
            tw.calc_v(level=level) 
        
    

        
        
        # optional, if you want to time it
        timer_gpu_T_fwd = GpuTimer()           
        
        # Simply calling 
        #   tic = time.clock()
        # and then 
        #   tic = time.clock()
        # won't work.
        # In fact, most likely you will get that toc-tic is zero.
        # You need to use the GpuTimer object. When you do that, 
        # one side effect is that suddenly the toc-tic from above will
        # give you a more realistic result.
        
        
        tic = time.clock() 
        timer_gpu_T_fwd.tic()
        tw.calc_T_fwd(pts_src,pts_fwd,level=level)
        timer_gpu_T_fwd.toc()   
        toc = time.clock()

        print 'Time, in sec, for computing T_fwd:'           
        print timer_gpu_T_fwd.secs
        print toc-tic  # likely to be 0, unless you also used the GpuTimer.
        
        # You can also time the inv of course. Results will be similar.
        tw.calc_T_inv(pts_src,pts_inv,level=level)  
             
        if eval_cell_idx:   
            # cell_idx is computed here just for display. 
            cell_idx = CpuGpuArray.zeros(len(pts_src),dtype=np.int32)
            tw.calc_cell_idx(pts_src,cell_idx,level,
                             permute_for_disp=permute_cell_idx_for_display)
 

        # If may also want ro to time the remap.
        # However, the remap is usually very fast (e.g, about 2 milisec).
#            timer_gpu_remap_fwd = GpuTimer()  
#            tic = time.clock()
#            timer_gpu_remap_fwd.tic()
#        tw.remap_fwd(pts_inv=pts_inv,img=img_original,img_wrapped_fwd=img_wrapped_fwd)
        tw.remap_fwd(pts_inv=pts_inv,img=img_original,img_wrapped_fwd=img_wrapped_fwd)
#            timer_gpu_remap_fwd.toc()   
#            toc = time.clock()   

        # If the img type is np.float32, you may also use 
        # tw.remap_fwd_opencv instead of tw.remap_fw. The differences between
        # the two methods are explained above  
                   
        
        
        tw.remap_inv(pts_fwd=pts_fwd,img=img_original,img_wrapped_inv=img_wrapped_bwd)
        
    
        # For display purposes, do gpu2cpu transfer
        print ("For display purposes, do gpu2cpu transfer")
        if eval_cell_idx:        
            cell_idx.gpu2cpu()  
            


            
            
            
        if eval_v:
            tw.v_dense.gpu2cpu() 
        pts_fwd.gpu2cpu()
        pts_inv.gpu2cpu()
        img_wrapped_fwd.gpu2cpu()
        img_wrapped_bwd.gpu2cpu()
        
        figsize = (12,12)
        plt.figure(figsize=figsize)

         
        if eval_v: 
            plt.subplot(332)
            tw.imshow_vx() 
            plt.title('vx')
            plt.subplot(333)
            tw.imshow_vy()   
            plt.title('vy') 
        
        if eval_cell_idx:
            plt.subplot(331)
            cell_idx_disp = cell_idx.cpu.reshape(img.shape[0],-1)
            plt.imshow(cell_idx_disp)
            plt.title('tess (type {})'.format(tess))
        
        if show_downsampled_pts:
            ds=20
            pts_src_grid = pts_src.cpu.reshape(tw.nRows,-1,2)
            pts_src_ds=pts_src_grid[::ds,::ds].reshape(-1,2)
            pts_fwd_grid = pts_fwd.cpu.reshape(tw.nRows,-1,2)
            pts_fwd_ds=pts_fwd_grid[::ds,::ds].reshape(-1,2)
            pts_inv_grid = pts_inv.cpu.reshape(tw.nRows,-1,2)
            pts_inv_ds=pts_inv_grid[::ds,::ds].reshape(-1,2)
        
           
            use_lims=use_lims_when_plotting
#            return tw
            plt.subplot(334)    
            plt.plot(pts_src_ds[:,0],pts_src_ds[:,1],'r.')
            plt.title('pts ds')
            tw.config_plt()
            plt.subplot(335)
            plt.plot(pts_fwd_ds[:,0],pts_fwd_ds[:,1],'g.')
            plt.title('fwd(pts)')
            tw.config_plt(axis_on_or_off='on',use_lims=use_lims)
            plt.subplot(336)
            plt.plot(pts_inv_ds[:,0],pts_inv_ds[:,1],'b.')
            plt.title('inv(pts)')
            tw.config_plt(axis_on_or_off='on',use_lims=use_lims)
         
                        
        plt.subplot(337)
        plt.imshow(img_original.cpu.astype(np.uint8))
        plt.title('img')
#        plt.axis('off') 
        plt.subplot(338)
        plt.imshow(img_wrapped_fwd.cpu.astype(np.uint8))
#        plt.axis('off') 
        plt.title('fwd(img)')
        plt.subplot(339)
        plt.imshow(img_wrapped_bwd.cpu.astype(np.uint8))    
#        plt.axis('off') 
        plt.title('inv(img)')
    
    
    return tw


if __name__ == '__main__':    
    tw = example()
#    Here are some other options you may want to try.
#    You can also try to combine these options, but note
#    that few of these combinations are invalid -- in which case 
#    an Exception will be thrown.
#    tw = example(tess='II') # OK
#    tw = example(nLevels=2) # OK
#    tw = example(base=[2,3]) # OK
#    tw = example(vol_preserve=True) # OK
#    tw = example(zero_v_across_bdry=[1,1],valid_outside=True) # Will fail (as it should)
#    tw = example(zero_v_across_bdry=[1,1]) # Will also fail, since valid_outside defaults to True
#    tw = example(zero_v_across_bdry=[1,1],valid_outside=False)  # OK
#    tw = example(tess='II',zero_v_across_bdry=[1,1]) # Will fail (as it should) 
                                                      # as there are too many constraints
                                                      # The problem is that base=[1,1]
                                                      # means we have only one cell, 
                                                      # so with the added boundary constraints. 
                                                      # there are no degrees of freedom.
#    tw = example(tess='II',zero_v_across_bdry=[1,1],base=[1,2]) # OK
#    tw = example(tess='II',zero_v_across_bdry=[1,1],base=[2,2]) # OK
#    tw =example(zero_v_across_bdry=[1,1],valid_outside=False,vol_preserve=True) # Will fail; no DoF.
#    tw =example(zero_v_across_bdry=[1,1],valid_outside=False,vol_preserve=True,base=[1,2]) # OK
#     For the effect of scale_spatial on the prior's smoothness, compare the following two lines
#    tw = example(scale_spatial=.01,base=[4,4],nLevels=1) # OK
#    tw = example(scale_spatial=10,base=[4,4],nLevels=1) # OK
#     For the effect of scale_value on the prior's variance, compare the following two lines
#    tw = example(scale_value=100.0,base=[4,4],nLevels=1) # OK
#    tw = example(scale_value=300.0,base=[4,4],nLevels=1) # OK
    
    
    if not inside_spyder():
        raw_input('Press Enter to exit')
    
