import sys
from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need to be fine-tuned.
build_exe_options = {
    "excludes": ['PyQt5'],
    'packages': ['imagej', 'PySimpleGUI', 'caiman', 'ipyparallel', 'skimage', 'seaborn'],
    'include_files': ['config.ini', 'Fiji.app', 'cache'],
    'silent_level': ['1']
}

msi_data = {
    "Icon": [
        ("IconId", "icon.ico"),
    ],
}

bdist_msi_options = {
    # "add_to_path": True,
    # "data": msi_data,
    # "environment_variables": [
    #     ("E_MYAPP_VAR", "=-*MYAPP_VAR", "1", "TARGETDIR")
    # ],
    # "upgrade_code": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}",
}

# base="Win32GUI" should be used only for Windows GUI app
base = "Win32GUI" if sys.platform == "win32" else None

executables = [
    Executable(
        'main_GUI.py',
        base=base
    )
]

setup(
    name="pipeline",
    version="0.1",
    description="Test on build for incomplete GUI application",
    options={
        "build_exe": build_exe_options,
        "build_msi": bdist_msi_options,
    },
    executables=executables,
)
