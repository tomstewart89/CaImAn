from __future__ import print_function
import caiman as cm
from caiman.source_extraction import cnmf as cnmf
from caiman.cluster import start_server, stop_server
import numpy.testing as npt
import numpy as np
import psutil


def demo(parallel=False):

    # roughly number of cores on your machine minus 1
    n_processes = np.maximum(psutil.cpu_count() - 2, 1)
    p = 2  # order of the AR model (in general 1 or 2)
    stop_server()
    if parallel:
        start_server()

    # LOAD MOVIE AND MEMORYMAP
    fname_new = cm.save_memmap(['example_movies/demoMovie.tif'], base_name='Yr')
    Yr, dims, T = cm.load_memmap(fname_new)
    # INIT
    cnm = cnmf.CNMF(n_processes, method_init='greedy_roi', k=30, gSig=[4, 4], merge_thresh=.8,
                    p=p, dview=None, Ain=None, method_deconvolution='oasis')
    # FIT
    images = np.reshape(Yr.T, [T] + list(dims), order='F')
    cnm = cnm.fit(images)
    if parallel:
        stop_server()

    # verifying the spatial components
    npt.assert_allclose(cnm.A.sum(), 32282000, 1e-3)
    # verifying the temporal components
    npt.assert_allclose(cnm.C.sum(), 640.5, 1e-2)


def test_single_thread():
    demo()


def test_parallel():
    demo(True)
