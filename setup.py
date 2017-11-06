# Copyright 2016 Sean Robertson

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import platform

from codecs import open
from os import environ
from os import path
from os import walk
from setuptools import setup
from setuptools.command.build_ext import build_ext
from setuptools.extension import Extension
from sys import maxsize
from sys import stderr
from sys import version_info

IS_64_BIT = maxsize > 2 ** 32

def mkl_setup(mkl_root, mkl_threading=None):
    mkl_root = path.abspath(mkl_root)
    found_mkl_libs = {
        'mkl_rt': False,
        'mkl_intel': False,
        'mkl_intel_lp64': False,
        'mkl_intel_thread': False,
        'mkl_gnu_thread': False,
        'mkl_sequential': False,
        'mkl_tbb_thread': False,
    }
    blas_library_dirs = set()
    blas_includes = set()
    for root_name, _, base_names in walk(mkl_root):
        for base_name in base_names:
            library_name = base_name[3:].split('.')[0]
            if library_name in found_mkl_libs:
                found_mkl_libs[library_name] = True
                blas_library_dirs.add(root_name)
            elif base_name == 'mkl.h':
                blas_includes.add(root_name)
    if not blas_includes:
        raise Exception('Could not find mkl.h')
    blas_library_dirs = list(blas_library_dirs)
    blas_includes = list(blas_includes)
    if mkl_threading is None:
        if found_mkl_libs['mkl_rt']:
            mkl_threading = 'dynamic'
        elif found_mkl_libs['mkl_intel_thread']:
            mkl_threading = 'intel'
        elif found_mkl_libs['mkl_tbb_thread']:
            mkl_threading = 'tbb'
        elif found_mkl_libs['mkl_sequential']:
            mkl_threading = 'sequential'
        elif found_mkl_libs['mkl_gnu_thread']:
            mkl_threading = 'gnu'
        else:
            raise Exception('Could not find a threading library for MKL')
    if mkl_threading == 'dynamic':
        blas_libraries = ['mkl_rt']
    else:
        blas_libraries = ['mkl_intel_lp64'] if IS_64_BIT else ['mkl_intel']
        if mkl_threading in ('intel', 'iomp'):
            blas_libraries += ['mkl_intel_thread', 'iomp5']
        elif mkl_threading in ('gnu', 'gomp'):
            blas_libraries += ['mkl_gnu_thread', 'gomp']
        elif mkl_threading == 'tbb':
            blas_libraries.append('mkl_tbb_thread')
        elif mkl_threading == 'sequential':
            blas_libraries.append('mkl_sequential')
        else:
            raise Exception(
                'Invalid MKL_THREADING_TYPE: {}'.format(mkl_threading))
        blas_libraries.append('mkl_core')
    if not all(found_mkl_libs[lib] for lib in blas_libraries):
        raise Exception('MKL_THREADING_TYPE=={} requires {} libs'.format(
            mkl_threading, blas_libraries))
    return {
        'BLAS_LIBRARIES': blas_libraries,
        'BLAS_LIBRARY_DIRS': blas_library_dirs,
        'BLAS_INCLUDES': blas_includes,
        'LD_FLAGS': ['-Wl,--no-as-needed'],
        'DEFINES': [('HAVE_MKL', None)],
    }

def blas_setup(root, library_names, headers, extra_entries_on_success):
    root = path.abspath(root)
    library_names = dict((lib, False) for lib in library_names)
    headers = dict((header, False) for header in headers)
    library_dirs = set()
    include_dirs = set()
    for root_name, _, base_names in walk(root):
        for base_name in base_names:
            library_name = base_name[3:].split('.')[0]
            if library_name in library_names:
                library_names[library_name] = True
                library_dirs.add(root_name)
            elif base_name in headers:
                headers[base_name] = True
                include_dirs.add(root_name)
    if not all(library_dirs.values()):
        raise Exception('Could not find {}'.format(
            tuple(key for key, val in library_dirs.items() if not val)))
    if not all(headers.values()):
        raise Exception('Could not find {}'.format(
            tuple(key for key, val in headers.items() if not val)))
    ret = dict(extra_entries_on_success)
    ret['BLAS_LIBRARIES'] = library_names
    ret['BLAS_LIBRARY_DIRS'] = list(library_dirs)
    ret['BLAS_INCLUDES'] = list(include_dirs)
    return ret

def openblas_setup(openblas_root):
    return blas_setup(
        openblas_root,
        ('openblas',),
        ('cblas.h', 'lapacke.h',),
        {'DEFINES': [('HAVE_OPENBLAS', None)]},
    )

def atlas_setup(atlas_root):
    return atlas_setup(
        atlas_root,
        ('atlas',),
        ('cblas.h', 'clapack.h',),
        {'DEFINES': [('HAVE_ATLAS', None)]},
    )

def accelerate_setup():
    return {
        'DEFINES': [('HAVE_CLAPACK', None)],
        'LD_FLAGS': ['-framework', 'Accelerate'],
    }

PWD = path.abspath(path.dirname(__file__))
PYTHON_DIR = path.join(PWD, 'python')
SRC_DIR = path.join(PWD, 'src')
SWIG_DIR = path.join(PWD, 'swig')
DEFINES = [
    ('KALDI_DOUBLEPRECISION', environ.get('KALDI_DOUBLEPRECISION', '0')),
    # ('_GLIBCXX_USE_CXX11_ABI', '0'),
    ('HAVE_EXECINFO_H', '1'),
    ('HAVE_CXXABI_H', None),
]
FLAGS = ['-std=c++11', '-m64' if IS_64_BIT else '-m32', '-msse', '-msse2']
FLAGS += ['-pthread', '-fPIC']
LD_FLAGS = []

MKL_ROOT = environ.get('MKLROOT', None)
OPENBLAS_ROOT = environ.get('OPENBLASROOT', None)
ATLAS_ROOT = environ.get('ATLASROOT', None)
if MKL_ROOT or OPENBLAS_ROOT or ATLAS_ROOT:
    if sum(x is None for x in (MKL_ROOT, OPENBLAS_ROOT, ATLAS_ROOT)) != 2:
        raise Exception(
            'Only one of MKLROOT, ATLASROOT, or OPENBLASROOT should be set')
    if MKL_ROOT:
        BLAS_DICT = mkl_setup(MKL_ROOT, environ.get('MKL_THREADING_TYPE', None))
    elif OPENBLAS_ROOT:
        BLAS_DICT = openblas_setup(OPENBLAS_ROOT)
    else:
        BLAS_DICT = atlas_setup(ATLAS_ROOT)
elif platform.system() == 'Darwin':
    print('Installing with accelerate')
    BLAS_DICT = accelerate_setup()
else:
    print(
'No BLAS library specified at command line. Will look via numpy. If you have '
'problems with linking, please specify BLAS via command line.')

BLAS_LIBRARIES = BLAS_DICT.get('BLAS_LIBRARIES', [])
BLAS_LIBRARY_DIRS = BLAS_DICT.get('BLAS_LIBRARY_DIRS', [])
BLAS_INCLUDES = BLAS_DICT.get('BLAS_INCLUDES', [])
LD_FLAGS += BLAS_DICT.get('LD_FLAGS', [])
DEFINES += BLAS_DICT.get('DEFINES', [])

if platform.system() == 'Darwin':
    FLAGS += ['-flax-vector-conversions', '-stdlib=libc++']
    LD_FLAGS += ['-stdlib=libc++']

# Get the long description from the README file
with open(path.join(PWD, 'README.rst'), encoding='utf-8') as f:
    LONG_DESCRIPTION = f.read()

SRC_FILES = [path.join(SWIG_DIR, 'pydrobert', 'kaldi.i')]
for base_dir, _, files in walk(SRC_DIR):
    SRC_FILES += [path.join(base_dir, f) for f in files if f.endswith('.cc')]

# https://stackoverflow.com/questions/2379898/
# make-distutils-look-for-numpy-header-files-in-the-correct-place
class CustomBuildExtCommand(build_ext):
    def look_for_blas(self):
        '''Look for blas libraries through numpy'''
        from numpy.distutils import system_info
        found_blas = False
        for info_name, define, setup_func in (
                ('mkl', 'HAVE_MKL', setup_mkl),
                ('openblas', 'HAVE_OPENBLAS', setup_openblas),
                ('atlas', 'HAVE_ATLAS', setup_atlas),
                ('accelerate', 'HAVE_CLAPACK', setup_accelerate)):
            info = system_info.get_info(info_name)
            if not info:
                continue
            if info_name == 'accelerate' or 'include_dirs' in info:
                # should be sufficient
                for key, value in info.items():
                    setattr(self, key, getattr(self, key) + value)
                self.define_macros.append((define, None))
                print('Using {}'.format(info_name))
                found_blas = True
                break
            elif 'library_dirs' not in info:
                continue
            # otherwise we try setting up in the library dirs, then in the
            # directories above them.
            lib_dirs = list(info['library_dirs'])
            lib_dirs += [path.abspath(path.join(x, '..')) for x in lib_dirs]
            for lib_dir in lib_dirs:
                try:
                    blas_dict = setup_func(lib_dir)
                except:
                    continue
                self.libraries += blas_dict.get('BLAS_LIBRARIES', [])
                self.runtime_library_dirs += blas_dict.get('BLAS_LIBRARY_DIRS', [])
                self.include_dirs += blas_dict.get('BLAS_INCLUDES', [])
                self.extra_link_args += blas_dict.get('LD_FLAGS', [])
                self.define_macros += blas_dict.get('DEFINES', [])
                print('Using {}'.format(info_name))
                found_blas = True
        if not found_blas:
            raise Exception('Unable to find BLAS library via numpy')

    def run(self):
        import numpy
        self.include_dirs.append(numpy.get_include())
        if not len(BLAS_DICT):
            self.look_for_blas()
        build_ext.run(self)

INSTALL_REQUIRES = ['numpy', 'six', 'future']
if version_info < (3, 0):
    INSTALL_REQUIRES.append('enum34')
SETUP_REQUIRES = ['pytest-runner', 'setuptools_scm']
TESTS_REQUIRE = ['pytest']

KALDI_LIBRARY = Extension(
    'pydrobert.kaldi._internal',
    sources=SRC_FILES,
    libraries=['pthread', 'm', 'dl'] + BLAS_LIBRARIES,
    runtime_library_dirs=BLAS_LIBRARY_DIRS,
    include_dirs=[SRC_DIR] + BLAS_INCLUDES,
    extra_compile_args=FLAGS,
    extra_link_args=LD_FLAGS,
    define_macros=DEFINES,
    swig_opts=['-c++', '-builtin', '-Wall', '-I{}'.format(SWIG_DIR)],
    language='c++',
)

setup(
    name='pydrobert-kaldi',
    use_scm_version=True,
    description='Swig bindings for kaldi',
    long_description=LONG_DESCRIPTION,
    url='https://github.com/pydrobert-kaldi',
    author='Sean Robertson',
    author_email='sdrobert@cs.toronto.edu',
    license='Apache 2.0',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Researchers',
        'License :: OSI Approved :: Apache 2.0',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    packages=['pydrobert', 'pydrobert.kaldi', 'pydrobert.kaldi.io'],
    cmdclass={'build_ext': CustomBuildExtCommand},
    setup_requires=SETUP_REQUIRES,
    install_requires=INSTALL_REQUIRES,
    tests_require=TESTS_REQUIRE,
    ext_modules=[KALDI_LIBRARY],
    namespace_packages=['pydrobert'],
    entry_points={
        'console_scripts': [
            'write-table-to-pickle = pydrobert.kaldi.command_line:'
            'write_table_to_pickle',
            'write-pickle-to-table = pydrobert.kaldi.command_line:'
            'write_pickle_to_table',
        ]
    }
)
