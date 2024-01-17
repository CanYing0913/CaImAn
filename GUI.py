import queue
import time
import tkinter as tk
import tkinter.messagebox
from tkinter import ttk, filedialog, messagebox
from src.src_pipeline import Pipeline, QC, GUI_instance
from src.message import Message
import json
from pathlib import Path
from threading import Thread
import logging
from multiprocessing import Process, Lock, Queue
import imagej
from typing import List, Optional

# ImageJ Instance with its lock
imagej_path = Path(__file__).parent.joinpath("Fiji.app")
ij = imagej.init(imagej_path, mode='interactive')
ij_lock = Lock()
queue_lock = Lock()


def test(lock, queue, instance_list, idx):
    # msg = Message(idx=idx, is_running=False, is_finished=False)
    msg = {'idx': idx, 'is_running': False, 'is_finished': False}
    print(f"putting first {msg}")
    queue.put(msg)
    time.sleep(5)
    # instance_list[idx].is_running = True
    msg['is_running'] = True
    print(f"putting second {msg}")
    queue.put(msg)
    time.sleep(20)
    # instance_list[idx].is_finished = True
    msg['is_finished'] = True
    print(f"putting third {msg}")
    queue.put(msg)


class GUI:
    __slots__ = [
        'logger',
        # GUI fields
        'root',
        'TAB_MAX',
        # Pipeline fields
        'instance_list',
        'process_list',
        'tab_list',
        'queue',
    ]

    def center(self, window, width: int, height: int):
        """
        Function to center any window on the screen

        Params:
            window: window to be centered
            width: width of the window
            height: height of the window
        """
        if self.root.screen_width == 0 or self.root.screen_height == 0:
            raise Exception("Screen size is not initialized")
        # Find the center point
        center_x = (self.root.screen_width - width) // 2
        center_y = (self.root.screen_height - height) // 2

        # Set the position of the window to the center of the screen
        window.geometry(f'{width}x{height}+{center_x}+{center_y}')

    def __init__(self):
        # Set up logging
        from datetime import datetime
        log_folder = Path(__file__).parent.joinpath("log")
        log_folder.mkdir(exist_ok=True)
        log_name = log_folder.joinpath(Path('log_' + datetime.now().strftime("%y%m%d_%H%M%S") + '.txt'))
        # logging.basicConfig(
        #     level=logging.DEBUG,
        #     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        #     filename=log_name, filemode='w',
        # )
        self.logger = logging.getLogger('GUI')
        self.logger.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(log_name)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                                      datefmt='%y-%m-%d %H:%M:%S')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        self.logger.debug('Logging setup finished.')
        # TODO:Read Configuration files
        pass
        self.queue = Queue()

        # Instance-related List
        self.TAB_MAX = 4
        self.instance_list: List[Optional[GUI_instance, Pipeline]] = list(None for _ in range(self.TAB_MAX))
        self.tab_list: List[Optional[tkinter.Frame]] = list(None for _ in range(self.TAB_MAX))
        self.process_list: List[Optional[Process]] = list(None for _ in range(self.TAB_MAX))

        # Initialize Main Window
        self.root = tk.Tk()
        self.root.title("CalciumZero")
        # Define the window size
        window_width = 1200
        window_height = 800

        # Get the screen dimension
        self.root.screen_width = self.root.winfo_screenwidth()
        self.root.screen_height = self.root.winfo_screenheight()

        # Set root to center
        self.center(self.root, window_width, window_height)

        # Create the Menu
        self.create_menu()

        # Create the Notebook
        self.root.notebook = ttk.Notebook(self.root)
        self.root.notebook.pack(expand=True, fill='both')

        # Set up the app
        self.setup()
        self.logger.debug('GUI setup finished.')

    def create_menu(self):
        # Create a Menu Bar
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)
        # Add 'File' Menu
        file_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="  File  ", menu=file_menu)

        # Add 'New' Menu Item
        # Function to create a parameter dialog

        file_menu.add_command(label="New Instance", command=self.new_instance_dialog)
        file_menu.add_command(label="New QC", command=self.new_qc_dialog)

    def new_instance_dialog(self):
        with open(Path(__file__).parent.joinpath("config.json"), "r") as f:
            param_dict = json.load(f)
        # Create a simple dialog window
        dialog = tk.Toplevel(self.root)
        dialog.title("New instance initialization")
        self.center(dialog, 800, 600)

        # Add fields for parameters (e.g., tab name)
        # TODO: Add more fields for other parameters
        # Add checkboxes
        def on_checkbox_change(idx, var):
            value = var.get()
            param_dict['run'][idx] = True if value else False

        checkbox_frame = tk.Frame(dialog)
        checkbox_frame.pack()
        run_1, run_2, run_3 = tk.IntVar(), tk.IntVar(), tk.IntVar()
        tk.Label(checkbox_frame, text="Run:").pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(checkbox_frame, text="Crop", variable=run_1,
                       command=lambda n=0, v=run_1: on_checkbox_change(n, v)).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(checkbox_frame, text="Stabilizer", variable=run_2,
                       command=lambda n=1, v=run_2: on_checkbox_change(n, v)).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(checkbox_frame, text="CaImAn", variable=run_3,
                       command=lambda n=2, v=run_3: on_checkbox_change(n, v)).pack(side=tk.LEFT, padx=5)

        # File/Folder selections
        ioselect_frame = tk.Frame(checkbox_frame)
        ioselect_frame.pack()

        # Input file selection
        def on_select_file():
            # Determine filetypes to use for file selection
            filetypes = [("TIF files", "*.tif"), ("All files", "*.*")]

            file_path = filedialog.askopenfilename(parent=dialog, title="Select a file", filetypes=filetypes)
            param_dict['input_path'] = file_path
            self.logger.debug(f"Selected input file: {file_path}")

        tk.Button(ioselect_frame, text="Select input File", command=on_select_file).pack(side=tk.LEFT, padx=5)

        # Output folder selection
        def on_select_folder():
            folder_path = filedialog.askdirectory(parent=dialog, title="Select a folder")
            param_dict['output_path'] = folder_path
            self.logger.debug(f"Selected output folder: {folder_path}")

        tk.Button(ioselect_frame, text="Select output Folder", command=on_select_folder).pack(side=tk.LEFT, padx=5)

        # Add param fields for each checkbox
        notebook = ttk.Notebook(dialog)
        notebook.pack(expand=True, fill='both')

        # Crop param tab
        tab_1 = ttk.Frame(notebook)
        tab_1.pack(expand=True)
        notebook.add(tab_1, text='Crop')

        def on_slider_change(event):
            param_dict['crop'].update(threshold=slider.get())

        # Create a container frame for the label and slider
        container_1 = ttk.Frame(tab_1)
        container_1.pack(expand=True)
        # Threshold Label
        label = ttk.Label(container_1, text=f"Threshold:")
        label.pack(side=tk.LEFT, padx=5)
        # Threshold Slider
        slider = tk.Scale(container_1, from_=0, to=500, orient='horizontal', resolution=10,
                          command=on_slider_change)
        slider.pack(side=tk.LEFT, padx=5)
        slider.set(param_dict['crop']['threshold'])

        # Validate input numbers
        def validate_numbers(num, type):
            if num == '':
                return (True, 0) if type is int else (True, 0.0)
            else:
                try:
                    return (True, int(num)) if type is int else (True, float(num))
                except ValueError:
                    return False, None

        # Stabilizer param tab
        tab_2 = ttk.Frame(notebook)
        tab_2.pack(expand=True)
        notebook.add(tab_2, text='Stabilizer')
        # Stabilizer containers
        for dname, d in param_dict['stabilizer'].items():
            def on_entry_change(value, key):
                status, val = validate_numbers(value, type(d))
                if not status and key != 'Transformation':
                    messagebox.showerror("Invalid Input", "Please enter a valid numeric value.")
                else:
                    param_dict['stabilizer'][key] = val

            container = ttk.Frame(tab_2)
            container.pack(expand=True)
            label = ttk.Label(container, text=dname)
            label.pack(padx=10, side=tk.LEFT)
            if type(d) is str:
                # A selection entry so user can select from a list
                var = tk.StringVar(value='Translation')
                trans_button = tk.Radiobutton(container, text="Translation", variable=var, value="Translation")
                trans_button.pack(padx=10, side=tk.LEFT)
                affine_button = tk.Radiobutton(container, text="Affine", variable=var, value="Affine")
                affine_button.pack(padx=10, side=tk.LEFT)
                trans_button.select()  # Set the Translation Radiobutton as the default selection
                var.trace_add("write",
                              lambda *args, text=var, key=dname: on_entry_change(text.get(), key))

                # Create a dummy Radiobutton with a value that is not used
                # dummy_button = tk.Radiobutton(container, variable=StrVar, value="dummy", state="disabled")
                # dummy_button.select()  # Set the dummy Radiobutton as the default selection
            else:
                # Text entry for numbers
                entry_text = tk.StringVar(value=d)
                entry = ttk.Entry(container, textvariable=entry_text)
                entry.pack(padx=10, side=tk.LEFT)
                entry_text.trace_add("write",
                                     lambda *args, text=entry_text, key=dname: on_entry_change(text.get(), key))

        # CaImAn param tab
        tab_3 = ttk.Frame(notebook)
        tab_3.pack(expand=True)
        notebook.add(tab_3, text='CaImAn')
        # CaImAn containers
        for dname, d in param_dict['caiman'].items():

            container_outer = ttk.Frame(tab_3)
            container_outer.pack(side=tk.LEFT, expand=True, fill='both', padx=5, pady=5)
            for k, v in d.items():
                def on_entry_change(value, key, dname=dname):
                    if type(value) is str:
                        status, val = validate_numbers(value, type(v))
                        if not status:
                            if key not in ['border_nan', 'method_init', 'method_deconvolution']:
                                messagebox.showerror("Invalid Input", "Please enter a valid numeric value.")
                            else:
                                if value == "None":
                                    param_dict['caiman'][dname][key] = None
                                else:
                                    param_dict['caiman'][dname][key] = value
                        # Numbers
                        else:
                            param_dict['caiman'][dname][key] = val
                    elif type(value) is bool:
                        param_dict['caiman'][dname][key] = True
                    elif type(value) is list:
                        status, val = validate_numbers(value[0], type(v))
                        if not status:
                            messagebox.showerror("Invalid Input", "Please enter a valid numeric value.")
                        else:
                            param_dict['caiman'][key] = [int(vi) if vi != '' else 0 for vi in value]
                    else:
                        raise NotImplementedError(f"Unknown type {type(value)} for value {value}.")

                if k == "fnames":
                    continue
                # Create a container frame for the label and entry
                container = ttk.Frame(container_outer)
                container.pack(expand=True)
                # Label
                label = ttk.Label(container, text=f"{k}:")
                label.pack(side=tk.LEFT, padx=5)
                # Entry type 1: strings
                if type(v) is str:
                    if k == 'border_nan':
                        var = tk.StringVar(value=v)

                        container_inner = ttk.Frame(container)
                        container_inner.pack()

                        # Radiobutton for True
                        copy_radio = tk.Radiobutton(container_inner, text="copy", variable=var, value="copy")
                        copy_radio.pack(side=tk.LEFT, padx=5)

                        # Radiobutton for False
                        none_radio = tk.Radiobutton(container_inner, text="None", variable=var, value="None")
                        none_radio.pack(side=tk.LEFT, padx=5)

                        var.trace_add("write",
                                      lambda *args, text=var, key=k: on_entry_change(text.get(), key))
                    elif k == 'method_init':
                        pass
                    else:  # "method_deconvolution"
                        pass
                # Entry type 2: True / False
                elif type(v) is bool:
                    var = tk.StringVar(value="True" if v else "False")

                    container_inner = ttk.Frame(container)
                    container_inner.pack()

                    # Radiobutton for True
                    true_radio = tk.Radiobutton(container_inner, text="True", variable=var, value="True")
                    true_radio.pack(side=tk.LEFT, padx=5)

                    # Radiobutton for False
                    false_radio = tk.Radiobutton(container_inner, text="False", variable=var, value="False")
                    false_radio.pack(side=tk.LEFT, padx=5)

                    var.trace_add("write",
                                  lambda *args, text=var, key=k: on_entry_change(
                                      True if text.get() == "True" else False, key))
                # Entry type 3: list[int, int]
                elif type(v) is list:
                    var = tk.StringVar(value=v[0])
                    container_inner = ttk.Frame(container)
                    container_inner.pack()
                    entry_1 = ttk.Entry(container_inner, textvariable=var, width=10)
                    entry_1.pack(side=tk.LEFT, padx=5)
                    entry_2 = ttk.Entry(container_inner, textvariable=var, width=10)
                    entry_2.pack(side=tk.LEFT, padx=5)
                    var.trace_add("write",
                                  lambda *args, text=var, key=k: on_entry_change([text.get(), text.get()], key))
                # Entry type 4: numbers
                else:
                    entry_text = tk.StringVar(value=v)
                    entry = ttk.Entry(container, textvariable=entry_text)
                    entry.pack(side=tk.LEFT, padx=5)
                    entry_text.trace_add("write",
                                         lambda *args, text=entry_text, key=k: on_entry_change(text.get(), key))

        # Function to handle 'OK' button click
        def on_ok():
            status, msg = self.create_instance(run_params=param_dict, run=True)
            if not status:
                self.logger.debug(f'Instance creation failed: {msg}')
                tkinter.messagebox.showerror("Error", f"Instance creation failed: {msg}")
                return
            dialog.destroy()
            self.logger.debug(f'New instance created and added to position {msg}.')

        # OK and Cancel buttons
        tk.Button(dialog, text="OK", command=on_ok).pack(side="left", padx=10, pady=10)
        tk.Button(dialog, text="Cancel", command=dialog.destroy).pack(side="right", padx=10, pady=10)

    def new_qc_dialog(self):
        qc_path = ''
        # Create a simple dialog window
        dialog = tk.Toplevel(self.root)
        dialog.title("New qc initialization")
        self.center(dialog, 400, 300)

        frame_1 = tk.Frame(dialog)
        frame_1.pack()

        # Input file selection
        def on_select_file():
            nonlocal qc_path
            # Determine filetypes to use for file selection
            filetypes = [("cmobj", "*.cmobj"), ("cm_obj", "*.cm_obj"), ("All files", "*.*")]

            qc_path = filedialog.askopenfilename(parent=dialog, title="Select a file", filetypes=filetypes)
            self.logger.debug(f"Selected qc file: {qc_path}")

        tk.Button(frame_1, text="Select QC File", command=on_select_file).pack(side=tk.LEFT, padx=5)

        frame_2 = tk.Frame(dialog)
        frame_2.pack()

        # Function to handle 'OK' button click
        def on_ok():
            if qc_path is None or qc_path == '':
                self.logger.debug(f'No qc file selected.')
                tkinter.messagebox.showerror("Error", "No qc file selected.")
                return

            status, msg = self.create_instance(qc_param={'cm_obj': qc_path}, run=False, qc=True)
            if not status:
                self.logger.debug(f'Instance creation failed: {msg}')
                tkinter.messagebox.showerror("Error", f"Instance creation failed: {msg}")
                return
            dialog.destroy()
            self.logger.debug(f'New QC instance created and added to position {msg}.')

        # OK and Cancel buttons
        tk.Button(frame_2, text="OK", command=on_ok).pack(side=tk.LEFT, padx=10, pady=10)
        tk.Button(frame_2, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=10, pady=10)

    # Function to create a new tab with given parameters
    def create_instance(self, run_params=None, qc_param=None, run=True, qc=False):
        # Find next available index
        try:
            idx = self.instance_list.index(None)
        except ValueError:
            return False, "Maximum number of instances reached."

        cur_instance = GUI_instance()
        if run:
            run_instance = Pipeline()
            cur_instance.run_instance = run_instance
            for item in ['input_path', 'output_path', 'run']:
                if item not in run_params:
                    return False, f"Missing parameter {item}."
            run_instance.update(params_dict=run_params)  # Setup parameters
            run_instance.update(logger=self.logger)  # Setup logger
            run_instance.update(
                queue=self.queue,
                queue_id=len(self.instance_list)
            )  # Setup queue
        if qc:
            qc_instance = QC(qc_param['cm_obj'])
            cur_instance.qc_instance = qc_instance

        self.instance_list[idx] = cur_instance
        self.process_list[idx] = None

        cur_tab = self.create_tab(self.root.notebook, idx, run=run, qc=qc)
        self.root.notebook.add(cur_tab, text='New Instance')
        self.tab_list[idx] = cur_tab
        return True, idx

    def create_tab(self, parent, idx, run=False, qc=False):
        cur_instance = self.instance_list[idx]
        instance_tab = ttk.Frame(parent)
        instance_tab.pack(expand=True, fill='both')
        instance_tab.id = idx
        instance_tab.run, instance_tab.qc = run, qc

        instance_tab.notebook = ttk.Notebook(instance_tab)
        instance_tab.notebook.pack(expand=True, fill='both')

        if run:
            run_tab = ttk.Frame()
            run_tab.pack(expand=True, fill='both')
            ss_button = ttk.Button(run_tab, text='Start', command=lambda id=instance_tab.id: self.run_instance(id))
            ss_button.pack(side='top', padx=5, pady=5)
            run_tab.ss_button = ss_button

            close_button = ttk.Button(run_tab, text='Close',
                                      command=lambda id=instance_tab.id: self.close_instance(id))
            close_button.pack(side='top', padx=5, pady=5)
            run_tab.close_button = close_button
            instance_tab.notebook.add(run_tab, text='Run')

        if qc:
            qc_instance = cur_instance.qc_instance
            qc_tab = ttk.Frame()
            qc_tab.pack(expand=True, fill='both')

            # #
            # from tifffile import TiffFile
            # qc_tab.movie = TiffFile(movie_path)
            qc_instance.qc_tab = qc_tab

            max_h, max_w = 500, 800
            h_, w_ = qc_instance.movie[0][0].shape
            if h_ > max_h or w_ > max_w:
                h_, w_ = int(h_ * min(max_h / h_, max_w / w_)), int(w_ * min(max_h / h_, max_w / w_))
            qc_tab.canvas = tk.Canvas(qc_tab, width=w_, height=h_)
            qc_tab.canvas.pack()
            qc_instance.show_frame(0)

            container = ttk.Frame(qc_tab)
            container.pack()

            # Define a callback function to update the scrollbar and canvas
            def update_scrollbar_and_canvas(value):
                frame_idx = int(value)
                qc_instance.show_frame(frame_idx)
                # Update the input field with the current frame number
                input_field.delete(0, tk.END)
                input_field.insert(0, str(frame_idx))

            # Define a callback function to update the scrollbar and canvas when the user types in the input field
            def update_scrollbar_and_canvas_from_input(event):
                try:
                    frame_idx = int(input_field.get())
                    if 0 <= frame_idx < len(qc_instance.movie):
                        qc_tab.scrollbar.set(frame_idx)
                        qc_instance.show_frame(frame_idx)
                except ValueError:
                    pass
            qc_tab.scrollbar = tk.Scale(container, from_=0, to=len(qc_instance.movie[0]) - 1, orient="horizontal",
                                        command=update_scrollbar_and_canvas, showvalue=False)
            qc_tab.scrollbar.pack(side=tk.LEFT, padx=5, pady=5)

            # Create an input field next to the scrollbar
            input_field = tk.Entry(container)
            input_field.pack(side=tk.LEFT, padx=5, pady=5)

            # Bind the input field to the update_scrollbar_and_canvas_from_input function
            input_field.bind("<Return>", update_scrollbar_and_canvas_from_input)

            instance_tab.notebook.add(qc_tab, text='QC')

        return instance_tab

    def close_instance(self, id: int):
        # Delete Pipeline instance and running Process
        if id < len(self.process_list):
            try:
                self.process_list[id].terminate()
                self.process_list[id] = None
            except AttributeError:
                pass
        self.instance_list[id] = None
        # Delete tab
        self.tab_list[id].destroy()
        self.tab_list[id] = None

    def instance_monitor(self):
        assert len(self.instance_list) == len(self.tab_list)
        try:
            while True:
                msg = self.queue.get_nowait()
                print(msg)
                # idx = msg.idx
                idx = msg['idx']
                if not self.tab_list[idx].run:
                    self.logger.error(f"Message received for a non-running instance {idx}.")
                    raise NotImplementedError(f"Message received for a non-running instance {idx}.")
                # if msg.is_running is not None:
                #     self.instance_list[idx].is_running = msg.is_running
                # if msg.is_finished is not None:
                #     self.instance_list[idx].is_finished = msg.is_finished
                # cur_pipeline = self.instance_list[idx]
                # if msg.is_finished:
                if msg['is_finished']:
                    print(f'finished {idx}')
                    self.tab_list[idx].notebook.tab(0).ss_button['text'] = 'Finished'
                    self.tab_list[idx].notebook.tab(0).ss_button.config(state=tk.DISABLED)
                # elif msg.is_running:
                elif msg['is_running']:
                    print(f'running {idx}')
                    self.tab_list[idx].notebook.tab(0).ss_button['text'] = 'Stop'
                    self.tab_list[idx].notebook.tab(0).ss_button.config(state=tk.NORMAL)
                else:
                    self.tab_list[idx].notebook.tab(0).ss_button['text'] = 'Start'
                    self.tab_list[idx].notebook.tab(0).ss_button.config(state=tk.NORMAL)
        except queue.Empty:
            pass
        finally:
            self.root.after(500, self.instance_monitor)

    def run_instance(self, idx):
        if self.instance_list[idx].is_running or self.instance_list[idx].is_finished:
            return
        # check running ok
        status, msg = self.instance_list[idx].ready()
        if not status:
            self.logger.debug(f'not ready, message: {msg}')
            raise Warning("Instance not ready")
        print(f'running {idx}')
        # p = Process(target=self.instance_list[idx].run, args=())
        # p.start()
        # self.process_list[idx] = p
        p = Process(target=test, args=(queue_lock, self.queue, self.instance_list, idx))
        p.start()
        self.process_list[idx] = p

    def setup(self):
        def on_close():
            if messagebox.askokcancel("Quit", "Do you want to quit the application?"):
                self.root.destroy()
                self.logger.debug('GUI closed.')

        self.root.protocol("WM_DELETE_WINDOW", on_close)

    def gui(self):
        try:
            self.instance_monitor()
            self.root.mainloop()
        except Exception as e:
            self.logger.error(e)


if __name__ == '__main__':
    gui = GUI()
    gui.gui()