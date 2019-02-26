from distutils.core import setup, Extension
import os

undef_macros = ["_DEBUG"]
define_macros = []
libraries = []
if hasattr(os, "fork"):
    undef_macros.append('MS_WINDOWS')
else:
    define_macros.append(('WIN32', 1))
    libraries.append('Ws2_32')

cpps = list()

files = os.listdir(".")
for f in files:
    parts = f.split(".")
    if len(parts) != 2:
        continue
    name, ext = parts
    if ext in ["cpp", "c"]:
        cpps.append(f)

setup(
    name='cares',
    ext_modules=[
        Extension('cares',
            cpps,
            define_macros = define_macros,
            undef_macros=undef_macros,
            libraries=libraries
        )
    ]
)