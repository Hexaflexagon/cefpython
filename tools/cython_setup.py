# Copyright (c) 2017 CEF Python, see the Authors file.
# All rights reserved. Licensed under BSD 3-clause license.
# Project website: https://github.com/cztomczak/cefpython

"""
cython_setup.py is for internal use only - called by build.py.
This is Cython's setup for building the cefpython module
"""

# Use setuptools so that "Visual C++ compiler for Python 2.7" tools
# can be used. Otherwise "Unable to find vcvarsall.bat" error occurs.
try:
    from setuptools import setup
    from setuptools import Extension
except ImportError:
    from distutils.core import setup
    from distutils.extension import Extension

# Use "Extension" from Cython.Distutils so that "cython_directives" works
from Cython.Distutils import build_ext, Extension
from Cython.Compiler import Options
# noinspection PyUnresolvedReferences
from Cython.Compiler.ModuleNode import ModuleNode
from common import *
import sys
import platform
import Cython
import os

# Must monkey patch Cython's ModuleNode to inject custom C++ code
# in the generated cefpython.cpp. This is a fix for an error on Mac:
# > ImportError: dynamic module does not define init function
# To get rid of CEF's undefined symbol error when importing module
# it was required to pass "-fvisibility=hidden" and "-Wl,-dead_strip"
# flags. However these flags cause the "initcefpython_py27" Python
# Module Initialization function to be hidden as well. To workaround
# this it is required to add default visibility attribute to the
# signature of that init function.
#
# Original definition in Python 2.7:
# | https://github.com/python/cpython/blob/2.7/Include/pyport.h
# > define PyMODINIT_FUNC extern "C" __declspec(dllexport) void
#
# Original definition in Python 3.4 / 3.5 / 3.6:
# > define PyMODINIT_FUNC extern "C" __declspec(dllexport) PyObject*

if MAC:
    g_generate_extern_c_macro_definition_old = (
            ModuleNode.generate_extern_c_macro_definition)

    def generate_extern_c_macro_definition(self, code):
        # This code is written to both cefpython.h and cefpython.cpp
        g_generate_extern_c_macro_definition_old(self, code)
        code.putln("// Added by: cefpython/tools/cython_setup.py")
        code.putln("#undef PyMODINIT_FUNC")
        if sys.version_info[:2] == (2, 7):
            code.putln("#define PyMODINIT_FUNC extern \"C\""
                       " __attribute__((visibility(\"default\"))) void")
        else:
            code.putln("#define PyMODINIT_FUNC extern \"C\""
                       " __attribute__((visibility(\"default\"))) PyObject*")
    # Overwrite Cython function
    ModuleNode.generate_extern_c_macro_definition = (
            generate_extern_c_macro_definition)


# Constants
FAST_FLAG = False

# Cython options. Stop on first error, otherwise hundreds
# of errors appear in the console.
Options.fast_fail = True


def main():
    print("[cython_setup.py] Python version: %s" % platform.python_version())
    print("[cython_setup.py] Python executable: %s" % sys.executable)
    print("[cython_setup.py] Cython version: %s" % Cython.__version__)

    global FAST_FLAG
    if len(sys.argv) > 1 and "--fast" in sys.argv:
        # Fast mode disables optimization flags
        print("[cython_setup.py] FAST mode enabled")
        FAST_FLAG = True
        sys.argv.remove("--fast")

    if len(sys.argv) <= 1:
        print(__doc__)
        sys.exit(1)

    compile_time_constants()
    options = dict()
    set_compiler_options(options)
    options["include_dirs"] = get_include_dirs()
    options["library_dirs"] = get_library_dirs()
    options["libraries"] = get_libraries()

    print("[cython_setup.py] Execute setup()")
    setup(
        name='cefpython_py%s' % PYVERSION,
        cmdclass={'build_ext': build_ext},
        ext_modules=get_ext_modules(options)
    )


def get_winsdk_lib():
    print("[cython_setup.py] Detect Windows SDK library directory")
    ret = ""
    if WINDOWS:
        if ARCH32:
            winsdk_libs = [
                r"C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Lib",
                r"C:\\Program Files\\Microsoft SDKs\\Windows\\v7.0\\Lib",
            ]
        elif ARCH64:
            winsdk_libs = [
                r"C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Lib\\x64",
                r"C:\\Program Files\\Microsoft SDKs\\Windows\\v7.0\\Lib\\x64",
            ]
        else:
            raise Exception("Unknown architecture")
        for lib in winsdk_libs:
            if os.path.exists(lib):
                ret = lib
                break
        if not ret:
            ret = winsdk_libs[0]
        if not os.path.exists(ret):
            raise Exception("Windows SDK Lib directory not found: %s"
                            % ret)
    return ret


def set_compiler_options(options):
    """Extends options and also sets environment variables."""
    print("[cython_setup.py] Set compiler options")

    extra_compile_args = list()
    extra_link_args = list()

    if WINDOWS:
        # /EHsc - using STL string, multimap and others that use
        #         C++ exceptions.
        #
        # /ignore:4217 - disable warnings such as this:
        #
        #   client_handler_py27_32bit.lib(client_handler.obj): warning LNK4217:
        #   locally defined symbol _RemovePythonCallbacksForFrame imported in
        #   function "public: virtual bool __thiscall
        #   ClientHandler::OnProcessMessageReceived
        #
        # The above warning LNK4217 is caused by the warning below which occurs
        # when building the client_handler.lib static library:
        extra_compile_args.extend(["/EHsc"])
        extra_link_args.extend(["/ignore:4217"])

    if LINUX or MAC:
        # Compiler flags
        if FAST_FLAG:
            extra_compile_args.append("-O0")
        else:
            extra_compile_args.append("-O3")

        extra_compile_args.extend([
                "-DNDEBUG",
                "-std=gnu++11",
        ])

    if LINUX:
        os.environ["CC"] = "g++"
        os.environ["CXX"] = "g++"

        if FAST_FLAG:
            extra_compile_args.extend(["-flto",
                                       "-std=gnu++11"])
            extra_link_args.extend(["-flto"])
        else:
            # Fix "ImportError ... undefined symbol ..." caused by CEF's
            # include/base/ headers by adding the -flto flag (Issue #230).
            # Unfortunately -flto prolongs compilation time significantly.
            # More on the other flags: https://stackoverflow.com/questions/
            # 6687630/ .
            extra_compile_args.extend(["-flto",
                                       "-fdata-sections",
                                       "-ffunction-sections",
                                       "-std=gnu++11"])
            extra_link_args.extend(["-flto",
                                    "-Wl,--gc-sections"])

    if MAC:
        # Compiler environment variables
        os.environ["CC"] = "c++"
        os.environ["CXX"] = "c++"

        # COMPILER ARGS

        # -Wno-return-type-c-linkage to ignore:
        # > warning: 'somefunc' has C-linkage specified, but returns
        # > user-defined type 'sometype' which is incompatible with C
        #
        # -Wno-constant-logical-operand to ignore:
        # > warning: use of logical '||' with constant operand

        extra_compile_args.extend([
                # Compile against libc++ otherwise error "symbol not found"
                # with cef::logging::LogMessage symbol. Also include -lc++
                # and -lc++abi libraries.
                "-stdlib=libc++",
                "-Wno-return-type-c-linkage",
                "-Wno-constant-logical-operand",
        ])
        # From upstream CEF cefclient
        extra_compile_args.extend([
                "-fno-strict-aliasing",
                "-fno-rtti",
                "-fno-threadsafe-statics",
                "-fobjc-call-cxx-cdtors",
                # Visibility of symbols:
                "-fvisibility=hidden",
                "-fvisibility-inlines-hidden",
        ])
        # Visibility of symbols
        extra_compile_args.extend([
                # "-flto",
                # "-fdata-sections",
                # "-ffunction-sections",
        ])

        # LINKER ARGS
        extra_link_args.extend([
                "-mmacosx-version-min=10.9",
                "-Wl,-search_paths_first",
                "-F"+os.path.join(CEF_BINARIES_LIBRARIES, "bin"),
                "-framework", "Chromium Embedded Framework",
                "-Wl,-rpath,@loader_path/",  # ending slash is crucial!
        ])
        if not FAST_FLAG:
            extra_link_args.extend([
                    # "-force_flat_namespace",
                    # "-flto",
                    "-Wl,-dead_strip",
            ])

    options["extra_compile_args"] = extra_compile_args
    options["extra_link_args"] = extra_link_args


def get_include_dirs():
    print("[cython_setup.py] Prepare include directories")
    include_dirs = list()
    common_include_dirs = [
        SRC_DIR,
        os.path.join(SRC_DIR, "common"),
        os.path.join(SRC_DIR, "extern"),
        os.path.join(SRC_DIR, "extern", "cef")
    ]
    if WINDOWS:
        include_dirs.extend([WINDOWS_DIR])
        include_dirs.extend(common_include_dirs)
    elif MAC:
        include_dirs.extend([MAC_DIR])
        include_dirs.extend(common_include_dirs)
        # TODO: Check these directories, are these really required on Mac?
        include_dirs.extend([
            '/usr/include/gtk-2.0',
            '/usr/include/glib-2.0',
            '/usr/include/gtk-unix-print-2.0',
            '/usr/include/cairo',
            '/usr/include/pango-1.0',
            '/usr/include/gdk-pixbuf-2.0',
            '/usr/include/atk-1.0',
            # Fedora
            '/usr/lib64/gtk-2.0/include',
            '/usr/lib64/gtk-unix-print-2.0',
            '/usr/lib64/glib-2.0/include',
            '/usr/lib/gtk-2.0/include',
            '/usr/lib/gtk-2.0/gtk-unix-print-2.0',
            '/usr/lib/glib-2.0/include',
        ])
    elif LINUX:
        include_dirs.extend([LINUX_DIR])
        include_dirs.extend(common_include_dirs)
        include_dirs.extend([
            '/usr/include/gtk-2.0',
            '/usr/include/glib-2.0',
            '/usr/include/gtk-unix-print-2.0',
            '/usr/include/cairo',
            '/usr/include/pango-1.0',
            '/usr/include/gdk-pixbuf-2.0',
            '/usr/include/atk-1.0',
            # Ubuntu
            '/usr/lib/x86_64-linux-gnu/gtk-2.0/include',
            '/usr/lib/x86_64-linux-gnu/gtk-unix-print-2.0',
            '/usr/lib/x86_64-linux-gnu/glib-2.0/include',
            '/usr/lib/i386-linux-gnu/gtk-2.0/include',
            '/usr/lib/i386-linux-gnu/gtk-unix-print-2.0',
            '/usr/lib/i386-linux-gnu/glib-2.0/include',
            # Fedora
            '/usr/lib64/gtk-2.0/include',
            '/usr/lib64/gtk-unix-print-2.0',
            '/usr/lib64/glib-2.0/include',
            '/usr/lib/gtk-2.0/include',
            '/usr/lib/gtk-2.0/gtk-unix-print-2.0',
            '/usr/lib/glib-2.0/include',
        ])
    return include_dirs


def get_library_dirs():
    print("[cython_setup.py] Prepare library directories")
    library_dirs = [
        os.path.join(CEF_BINARIES_LIBRARIES, "lib"),
    ]
    if WINDOWS:
        library_dirs.extend([
            get_winsdk_lib(),
            os.path.join(SRC_DIR, "client_handler",
                         "Release_py{pyver}_{os}"
                         .format(pyver=PYVERSION, os=OS_POSTFIX2)),
            os.path.join(SRC_DIR, "subprocess",
                         "Release_{os}"
                         .format(os=OS_POSTFIX2)),
            os.path.join(SRC_DIR, "subprocess",
                         "Release_py{pyver}_{os}"
                         .format(pyver=PYVERSION, os=OS_POSTFIX2)),
            os.path.join(SRC_DIR, "cpp_utils",
                         "Release_{os}"
                         .format(os=OS_POSTFIX2))
        ])
    if MAC:
        library_dirs.append(os.path.join(CEF_BINARIES_LIBRARIES, "bin"))
    if MAC or LINUX:
        library_dirs.extend([
            os.path.join(SRC_DIR, "client_handler"),
            os.path.join(SRC_DIR, "subprocess"),  # libcefpythonapp
            os.path.join(SRC_DIR, "cpp_utils"),
        ])
    return library_dirs


def get_libraries():
    print("[cython_setup.py] Prepare libraries")
    libraries = list()
    if WINDOWS:
        libraries.extend([
            "libcef",
            "libcef_dll_wrapper_md",
            "User32",
            "client_handler_py{pyver}_{os}".format(
                    pyver=PYVERSION, os=OS_POSTFIX2),
            "libcefpythonapp_py{pyver}_{os}".format(
                    pyver=PYVERSION, os=OS_POSTFIX2),
            "cpp_utils_{os}".format(
                    os=OS_POSTFIX2),
        ])
    elif MAC:
        libraries.extend([
            "c++",
            "c++abi",
            "cef_dll_wrapper",
            "cefpythonapp",
            "client_handler",
            "cpp_utils",
        ])
    elif LINUX:
        libraries.extend([
            "X11",
            "gobject-2.0",
            "glib-2.0",
            "gtk-x11-2.0",
            # CEF and CEF Python libraries
            "cef_dll_wrapper",
            "cefpythonapp",
            "client_handler",
            "cpp_utils",
        ])
    return libraries


def get_ext_modules(options):
    ext_modules = [Extension(
        name=MODULE_NAME_NOEXT,
        sources=["cefpython.pyx"],

        # Ignore the warning in the console:
        # > C:\Python27\lib\distutils\extension.py:133: UserWarning:
        # > Unknown Extension options: 'cython_directives' warnings.warn(msg)
        cython_directives={
            # Any conversion to unicode must be explicit using .decode().
            "c_string_type": "bytes",
            "c_string_encoding": "utf-8",
        },

        language="c++",

        include_dirs=options["include_dirs"],
        library_dirs=options["library_dirs"],

        # Static libraries only. Order is important, if library A depends on B,
        # then B must be included before A.
        libraries=options["libraries"],

        # When you put "./" in here, loading of libcef.so will only work when
        # running scripts from the same directory that libcef.so resides in.
        # runtime_library_dirs=[
        #    './'
        # ],

        extra_compile_args=options["extra_compile_args"],
        extra_link_args=options["extra_link_args"],

        # Defining macros:
        # define_macros = [("UNICODE","1"), ("_UNICODE","1"), ]
    )]
    return ext_modules


def compile_time_constants():
    print("[cython_setup.py] Generate compile_time_constants.pxi")
    with open(os.path.join(SRC_DIR, "compile_time_constants.pxi"), "w") as fd:
        fd.write('# This file was generated by setup.py\n')
        # A way around Python 3.2 bug: UNAME_SYSNAME is not set
        fd.write('DEF UNAME_SYSNAME = "%s"\n' % platform.uname()[0])
        fd.write('DEF PY_MAJOR_VERSION = %s\n' % sys.version_info.major)


if __name__ == "__main__":
    main()
