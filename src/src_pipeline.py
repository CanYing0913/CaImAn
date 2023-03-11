"""
Source file for pipeline in general, OOP workflow
Last edited on Dec.31 2022
Copyright Yian Wang (canying0913@gmail.com) - 2022
"""
import argparse
from multiprocessing import Pool

import imagej

from src.src_caiman import *
# Retrieve source
from src.src_detection import *
from src.src_stabilizer import print_param, run_plugin
from src.src_peak_caller import PeakCaller


def remove_suffix(input_string, suffix):
    if suffix and input_string.endswith(suffix):
        return input_string[:-len(suffix)]
    return input_string


def parse():
    """
    Parse function for argparse
    """
    # Set up description
    desp = 'Automated pipeline for CaImAn processing.\nIf you have multiple inputs, please place them within a ' \
           'single folder without any other files.'
    parser = argparse.ArgumentParser(description=desp)
    # Set up arguments
    # Control parameters
    parser.add_argument('-no_log', default=False, action='store_true',
                        help='Specified if do not want to have terminal printouts saved to a separate file.')
    parser.add_argument('-ijp', '--imagej-path', type=str, metavar='ImageJ-Path', required=True,
                        help='Path to local Fiji ImageJ fiji folder.')
    parser.add_argument('-wd', '--work-dir', type=str, metavar='Work-Dir', required=True,
                        help='Path to a working folder where all intermediate and overall results are stored. If not '
                             'exist then will create one automatically.')
    parser.add_argument('-input', type=str, metavar='INPUT', required=True,
                        help='Path to input/inputs folder. If you have multiple inputs file, please place them inside '
                             'a single folder. If you only have one input, either provide direct path or the path to'
                             ' the folder containing the input(without any other files!)')
    parser.add_argument('-do_s0', default=True, action="store_false", required=False, help='Skip cropping if specified')
    parser.add_argument('-do_s1', default=True, action="store_false", required=False,
                        help='Skip Stabilizer if specified.')
    parser.add_argument('-do_s2', default=True, action="store_false", required=False,
                        help='Skip CaImAn if specified.')
    # Functional parameters
    parser.add_argument('-margin', default=200, type=int, metavar='Margin', required=False,
                        help='Margin in terms of pixels for auto-cropping. Default to be 200.')
    parser.add_argument('-ij_trans', default=0, type=int, required=False,
                        help='ImageJ stabilizer parameter - Transformation. You have to specify -ij_param to use it. '
                             'Default to translation, set it to 1 if want to set it to affine.')
    parser.add_argument('-ij_maxpl', default=1, type=float, required=False,
                        help='ImageJ stabilizer parameter - MAX_Pyramid_level. You have to specify -ij_param to use '
                             'it. Default to be 1.0.')
    parser.add_argument('-ij_upco', default=0.90, type=float, required=False,
                        help='ImageJ stabilizer parameter - update_coefficient. You have to specify -ij_param to use '
                             'it. Default to 0.90.')
    parser.add_argument('-ij_maxiter', default=200, type=int, required=False,
                        help='ImageJ stabilizer parameter - MAX_iteration. You have to specify -ij_param to use it. '
                             'Default to 200.')
    parser.add_argument('-ij_errtol', default=1E-7, type=float, required=False,
                        help='ImageJ stabilizer parameter - error_rolerance. You have to specify -ij_param to use '
                             'it. Default to 1E-7.')
    parser.add_argument('-clog', default=False, action='store_true',
                        help='True if enable logging for caiman part. Default to be false.')
    parser.add_argument('-csave', default=False, action='store_true',
                        help='True if want to save denoised movie. Default to be false.')
    # Parse the arguments
    arguments = parser.parse_args()
    # Post-process arguments
    # ImageJ path and param
    # arguments.imagej_path = Path(arguments.imagej_path)
    if not os.path.exists(arguments.imagej_path):
        if not arguments.skip_1:
            raise OSError(f"[ERROR]: ImageJ path does not exist: {arguments.imagej_path}")
    arguments.ij_params = [
        arguments.ij_trans,
        arguments.ij_maxpl,
        arguments.ij_upco,
        arguments.ij_maxiter,
        arguments.ij_errtol
    ]
    # work_dir path
    # arguments.work_dir = Path(arguments.work_dir)
    if not os.path.exists(arguments.work_dir):
        print(f"Working directory {arguments.work_dir} does not exist. Attempting to create one.")
        try:
            Path(arguments.work_dir).mkdir(parents=True, exist_ok=False)
        except OSError:
            print(f"[ERROR]: OSError detected. Please check if disk exists or privilege level satisfies.")
            exit(1)
    # input folder path
    arguments.input = str(arguments.input)  # To suppress IDE warning
    if os.path.exists(arguments.input):
        if os.path.isdir(arguments.input):
            # Path to a folder of multiple inputs.
            arguments.input_root = arguments.input
            arguments.input = [f for f in os.listdir(arguments.input_root) if f[-4:] == '.tif']
        else:
            # Path to a single input file.
            temp = os.path.basename(arguments.input)
            if temp[-4:] != ".tif":
                raise FileNotFoundError(f"The input file {arguments.input} is not a tiff file.")
            arguments.input_root = remove_suffix(arguments.input, temp)
            arguments.input = [temp]
    else:
        raise FileNotFoundError(f"[ERROR]: Input file path {arguments.input} does not exist.")
    return arguments


class Pipeline(object):
    def __init__(self):
        # Control sequence
        self.skip_0 = self.skip_1 = False
        self.work_dir = ''
        self.log = None
        self.process = 2
        # Segmentation and cropping related variables
        self.do_s0 = False
        self.input_root = ''
        self.input_list = []
        self.margin = 200
        self.imm1_list = []  # Intermediate result list 1, relative path
        self.done_s0 = False
        # ImageJ stabilizer related variables
        self.do_s1 = False
        self.ij = None
        self.ijp = ''
        self.s1_params = []
        self.s1_root = ''
        self.imm2_list = []  # Intermediate result list 2, relative path
        self.done_s1 = False
        # CaImAn related variables
        self.do_s2 = False
        self.caiman_obj = None
        self.clog = False
        self.csave = False
        self.s2_root = ''
        self.done_s2 = False
        # Peak Caller related
        self.pc_obj = []

    def pprint(self, txt: str):
        """
        Customized print function that both print to stdout and log file
        """
        print(txt)
        if self.log is not None:
            self.log.write(txt + '\n')

    def parse(self):
        # Retrieve calling parameters
        arguments = parse()

        # Must only specify one skip
        assert self.skip_0 is False or self.skip_1 is False, "Duplicate skip param specified."
        self.s1_root = self.s2_root = self.work_dir
        # Use parameters to set up pipeline global info
        # Control related
        self.work_dir = arguments.work_dir
        self.skip_0 = arguments.skip_0
        self.skip_1 = arguments.skip_1
        if not arguments.no_log:
            log_path = os.path.join(self.work_dir, 'log.txt')
            self.log = open(log_path, 'w')
            self.pprint(f"log file is stored @ {log_path}")
        # Segmentation and cropping related variables
        self.input_root = arguments.input_root
        self.input_list = arguments.input
        self.margin = arguments.margin
        # ImageJ related
        if not self.skip_1:
            self.ij = imagej.init(arguments.imagej_path, mode='headless')
            self.ijp = arguments.imagej_path
            self.pprint(f"ImageJ initialized with version {self.ij.getVersion()}.")
            self.s1_params = arguments.ij_params
            print_param(self.s1_params, self.pprint)
        # CaImAn related variables
        # TODO: add caiman parameters
        self.clog = arguments.clog
        self.csave = arguments.csave
        # TODO: add peak_caller parameters
        pass
        # Get control params to determine dest list
        # TODO: need extra care for caiman mmap generation

        # End of parser. Start of post-parse processing.
        if self.skip_0:
            self.s1_root = self.input_root
            self.imm1_list = self.input_list
        elif self.skip_1:
            self.s2_root = self.input_root
            self.imm2_list = self.input_list
        return None

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if not hasattr(self, key):
                print(f'the requested key {key} does not exist.')
                continue
            # if key == 'ijp':

                # ij = imagej.init(value, mode='headless')
                # setattr(self, 'ij', ij)
            setattr(self, key, value)

    def ready(self):
        if not self.input_list:
            return False, 'Input not specified'
        if self.work_dir == '':
            return False, 'Output folder not set'
        if self.do_s0:
            for input_file in self.input_list:
                if '.tif' not in input_file:
                    return False, f'Wrong input format for crop: {input_file}'
        if self.do_s1:
            if self.ijp == '' or self.s1_params == []:
                return False, 'ImageJ not ready'
            for input_file in self.input_list:
                if '.tif' not in input_file:
                    return False, f'Wrong input format for Stabilizer: {input_file}'
        if self.do_s2:
            pass
        return True, ''

    def s0(self):
        """
        Function to run segmentation, detection and cropping.

        Parameters:

        """
        def ps0(text: str):
            self.pprint(f"***[S0 - Detection]: {text}")

        # Segmentation and cropping
        # Scanning for bounding box for multiple input
        with Pool(processes=4) as pool:
            fnames = [join(self.input_root, fname) for fname in self.input_list]
            results = pool.map(scan, fnames)
        x1, y1, x2, y2 = reduce_bbs(results)

        # Apply the uniform bb one-by-one to each input image
        for fname_i in self.input_list:
            image_i = tifffile.imread(join(self.input_root, fname_i))
            image_crop_o = apply_bb_3d(image_i, (x1, y1, x2, y2), self.margin)
            # Handle output path
            fname_crop_root = remove_suffix(fname_i, '.tif') + '_crop.tif'
            fname_crop_o = os.path.join(self.work_dir, fname_crop_root)
            ps0(f"Using paths: {fname_crop_o} to save cropped result.")
            # Save imm1 data to files
            tifffile.imwrite(fname_crop_o, image_crop_o)
            self.imm1_list.append(fname_crop_root)
        self.done_s0 = True
        return

    def s1(self):
        def ps1(text: str):
            self.pprint(f"***[S1 - ImageJ stabilizer]: {text}")

        # ImageJ Stabilizer
        ps1(f"Stabilizer Starting.")
        results = []
        start_t = time()
        idx = 0
        while idx < len(self.imm1_list):
            imm1_list = [self.imm1_list[idx+i] for i in range(self.process) if idx+i < len(self.imm1_list)]
            idx += self.process
            with Pool(processes=len(imm1_list)) as pool:
                results = pool.starmap(run_plugin, [(self.ijp, join(self.s1_root, imm1), self.work_dir, self.s1_params) for imm1 in imm1_list])
        end_t = time()
        duration = end_t - start_t
        ps1(f"Stabilizer finished. total of {int(duration)} s.")
        self.imm2_list = results  # note here is absolute path list

    def s2(self):
        def ps2(txt: str):
            self.pprint(f"***[S2 - caiman]: {txt}")

        # TODO: caiman
        if self.clog:
            logging.basicConfig(
                format="%(relativeCreated)12d [%(filename)s:%(funcName)20s():%(lineno)s] [%(process)d] %(message)s",
                level=logging.DEBUG)
        fnames = self.imm2_list
        fnames_out = [remove_suffix(f, '.tif') + '_caiman.tif' for f in fnames]
        mc_dict = {
            'fnames': fnames,
            'fr': frate,
            'decay_time': decay_time,
            'pw_rigid': pw_rigid,
            'max_shifts': max_shifts,
            'gSig_filt': gSig_filt,
            'strides': strides,
            'overlaps': overlaps,
            'max_deviation_rigid': max_deviation_rigid,
            'border_nan': border_nan
        }
        opts = params.CNMFParams(params_dict=mc_dict)
        # Motion Correction
        if motion_correct:
            # do motion correction rigid
            mc = MotionCorrect(fnames, dview=None, **opts.get_group('motion'))
            mc.motion_correct(save_movie=True)
            fname_mc = mc.fname_tot_els if pw_rigid else mc.fname_tot_rig
            if pw_rigid:
                bord_px = np.ceil(np.maximum(np.max(np.abs(mc.x_shifts_els)),
                                             np.max(np.abs(mc.y_shifts_els)))).astype(np.int)
            else:
                bord_px = np.ceil(np.max(np.abs(mc.shifts_rig))).astype(np.int)
                plt.figure()
                plt.subplot(1, 2, 1)
                plt.imshow(mc.total_template_rig)  # % plot template
                plt.subplot(1, 2, 2)
                plt.plot(mc.shifts_rig)  # % plot rigid shifts
                plt.legend(['x shifts', 'y shifts'])
                plt.xlabel('frames')
                plt.ylabel('pixels')
                plt.show()

            bord_px = 0 if border_nan == 'copy' else bord_px
            fname_mmap = cm.save_memmap(fname_mc, base_name='memmap_', order='C', border_to_0=bord_px)
        else:  # if no motion correction just memory map the file
            bord_px = 0
            fname_mmap = cm.save_memmap(fnames, base_name='memmap_', order='C', border_to_0=0, dview=None)
        ps2(f"mmap file saved to {fname_mmap}")

        # load memory mappable file
        Yr, dims, T = cm.load_memmap(fname_mmap)
        images = Yr.T.reshape((T,) + dims, order='F')

        opts.change_params(params_dict={'method_init': 'corr_pnr',  # use this for 1 photon
                                        'K': K,
                                        'gSig': gSig,
                                        'gSiz': gSiz,
                                        'merge_thr': merge_thr,
                                        'p': p,
                                        'tsub': tsub,
                                        'ssub': ssub,
                                        'rf': rf,
                                        'stride': stride_cnmf,
                                        'only_init': True,  # set it to True to run CNMF-E
                                        'nb': gnb,
                                        'nb_patch': nb_patch,
                                        'method_deconvolution': 'oasis',  # could use 'cvxpy' alternatively
                                        'low_rank_background': low_rank_background,
                                        'update_background_components': True,
                                        # sometimes setting to False improve the results
                                        'min_corr': min_corr,
                                        'min_pnr': min_pnr,
                                        'normalize_init': False,  # just leave as is
                                        'center_psf': True,  # leave as is for 1 photon
                                        'ssub_B': ssub_B,
                                        'ring_size_factor': ring_size_factor,
                                        }
                           )
        # Inspect summary images and set parameters
        # compute some summary images (correlation and peak to noise)
        cn_filter, pnr = cm.summary_images.correlation_pnr(images[::10], gSig=gSig[0],
                                                           swap_dim=False)  # change swap dim if output looks weird, it is a problem with tiffile
        # inspect the summary images and set the parameters
        nb_inspect_correlation_pnr(cn_filter, pnr)

        # Run the CNMF-E algorithm
        start_time_cnmf = time()
        cnm = cnmf.CNMF(n_processes=8, dview=None, Ain=Ain, params=opts)
        cnm.fit(images)
        exec_time_cnmf = time() - start_time_cnmf
        ps2(f"it takes {exec_time_cnmf // 60}m, {int(exec_time_cnmf % 60)}s to complete.")
        # ## Component Evaluation
        # the components are evaluated in three ways:
        #   a) the shape of each component must be correlated with the data
        #   b) a minimum peak SNR is required over the length of a transient
        #   c) each shape passes a CNN based classifier
        min_SNR = 3  # adaptive way to set threshold on the transient size
        r_values_min = 0.85  # threshold on space consistency (if you lower more components will be accepted, potentially
        # with worst quality)
        cnm.params.set('quality', {'min_SNR': min_SNR,
                                   'rval_thr': r_values_min,
                                   'use_cnn': False})
        cnm.estimates.evaluate_components(images, cnm.params, dview=None)

        ps2(' ***** ')
        ps2(f'Number of total components:  {len(cnm.estimates.C)}')
        ps2(f'Number of accepted components: {len(cnm.estimates.idx_components)}')

        # Get alll detected spatial components
        x, y = cnm.estimates.A.shape
        # the index of accepted components
        myidx = cnm.estimates.idx_components

        coordinate1 = np.reshape(cnm.estimates.A[:, myidx[1]].toarray(), dims, order='F')
        bl = coordinate1 > 0

        # setup blank merge arrays. One is from merge, the other is from overlapped areas
        merged = np.where(bl is True, 0, coordinate1)
        mhits = np.where(bl is True, 0, coordinate1)
        blm = merged > 0

        for i in myidx:
            coordinate2 = np.reshape(cnm.estimates.A[:, i].toarray(), dims, order='F')
            # %% generate boolean indexing
            bl2 = coordinate2 > 0
            ct2 = np.sum(bl2)
            blm = merged > 0
            # identify the overlapped components
            bli = np.logical_and(bl2, blm)
            cti = np.sum(bli)
            # calculate the portion of the overlapped
            percent = cti / ct2
            # print(percent)
            if percent < 0.25:
                # change the label of this component
                merged = np.where(bl2 is True, i + 1, merged)
                # exclude the overlapped areas
                merged = np.where(bli is True, 0, merged)
            else:
                # put the overlapped areas here
                mhits = np.where(bli is True, 999 + i, mhits)

        np.savetxt(os.path.join(self.work_dir, "coor_merged.csv"), merged, delimiter=",")
        np.savetxt(os.path.join(self.work_dir, "coor_mhits.csv"), mhits, delimiter=",")

        # Extract DF/F values
        (components, frames) = cnm.estimates.C.shape
        ps2(f"frames: {frames}")
        cnm.estimates.detrend_df_f(quantileMin=8, frames_window=frames)
        self.caiman_obj = cnm
        # reconstruct denoised movie
        if self.csave:
            denoised = cm.movie(cnm.estimates.A.dot(cnm.estimates.C)).reshape(dims + (-1,), order='F').transpose(
                [2, 0, 1])
            denoised.save(fnames_out)
            ps2(f"caiman denoised movie saved to {fnames_out}")
        path = os.path.join(self.work_dir, "cmn_obj")
        with open(path, "wb") as f:
            pickle.dump(cnm, f)
            ps2(f"object cnm dumped to {path}.")

    def s3(self):
        # TODO: peak_caller
        slice_num = _
        data = self.caiman_obj.estimates.C[:92, :]
        # TODO: get slice number to know how many to pass to peak caller
        filename = join(self.work_dir, '')
        # demo: a single image
        pc_obj = PeakCaller(data, filename)
        pc_obj.Detrender_2()
        pc_obj.Find_Peak()
        # The above code generates a PeakCaller object with peaks detected
        pc_obj.Print_ALL_Peaks()
        pc_obj.Raster_Plot()
        pc_obj.Histogram_Height()
        pc_obj.Histogram_Time()
        pc_obj.Correlation()
        # To save results, do something like this:
        pc_obj.Synchronization()
        pc_obj.Save_Result()
        self.pc_obj.append(pc_obj)

    def run(self):
        # TODO: need to adjust imm1_list, imm2_list, according to which section is the first section
        if not self.do_s0:
            self.s1_root = self.input_root
            self.imm1_list = self.input_list
        if not self.do_s1:
            self.imm2_list = self.input_list
        start_time = time()
        # First, decide which section to start execute
        if self.do_s0:
            # Do cropping
            self.s0()
            self.done_s0 = True
        if self.do_s1:
            # Do stabilizer
            self.s1()
            self.done_s1 = True
        if self.do_s2:
            # CaImAn part
            start_time_caiman = time()
            self.s2()
            end_time_caiman = time()
            exec_t = end_time_caiman - start_time_caiman
            self.pprint(f"caiman part took {exec_t // 60}m {int(exec_t % 60)}s.")
            self.done_s2 = True
        pass
        # Peak_caller part
        pass
        end_time = time()
        exec_t = end_time - start_time
        self.pprint(f"[INFO] pipeline.run() takes {exec_t // 60}m {int(exec_t % 60)}s to run in total.")
        if self.log is not None:
            self.log.close()


def main():
    # testobj = Pipeline()
    # testobj.parse()

    # Note: current testing methodology is WRONG
    # testobj.run()
    # testobj.s0()
    # testobj.s1()
    # testobj.s1()
    # testobj.s0()
    filename = r'D:\CanYing\Code\Columbia\cmn_obj'
    with open(filename, 'rb') as f:
        cmn = pickle.load(f)
    data = cmn.estimates.C[:92, :1500]
    dir = r"E:/test_dir/out/result"
    Caller_obj_1 = PeakCaller(data, dir)
    Caller_obj_1.Detrender_2()
    Caller_obj_1.Find_Peak()
    # The above code generates a PeakCaller object with peaks detected
    Caller_obj_1.Print_ALL_Peaks()
    Caller_obj_1.Raster_Plot()
    Caller_obj_1.Histogram_Height()
    Caller_obj_1.Histogram_Time()
    Caller_obj_1.Correlation()
    # To save results, do something like this:
    Caller_obj_1.Synchronization()
    Caller_obj_1.Save_Result()


if __name__ == '__main__':
    main()
    exit(0)
