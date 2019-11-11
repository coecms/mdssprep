#!/usr/bin/env python

"""
Copyright 2017 ARC Centre of Excellence for Climate Systems Science

author: Aidan Heerdegen <aidan.heerdegen@anu.edu.au>

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import print_function

import pytest
import imp
from numpy import array, arange, dtype
from numpy.testing import assert_array_equal, assert_array_almost_equal
import os, sys
from pathlib import Path
from shutil import rmtree

import tarfile

sys.path.insert(1, os.path.join(sys.path[0], '..'))

from mdssprep import mdssprep, verify, set_policy

verbose = True

set_policy(compress=None)

root = Path('test') / Path('test_dir')

def make_file(path,size):
    with open(path, "w") as file:
        file.truncate(size)

def make_test_files():
    root.mkdir(parents=False,exist_ok=True)
    for f in range(1,30):
        make_file(root / Path("file_"+str(f)),mdssprep.one_meg*f)
    for f in range(50,200,50):
        make_file(root / Path("file_"+str(f)),mdssprep.one_meg*f)

def del_test_files():
    for f in root.glob('*'):
        f.unlink()

def setup_module(module):
    if verbose: print ("setup_module      module:%s" % module.__name__)
    del_test_files()
    make_test_files()
 
def teardown_module(module):
    if verbose: print ("teardown_module   module:%s" % module.__name__)
    # del_test_files()

def test_make_directory_class():
    t = mdssprep.Directory('test/test_dir')
    t.archive(dryrun=True)
    t = mdssprep.Directory('test/test_dir',exclude=['file_*3*','file_2??'],include=['file_*5*'],compress=None,maxarchivesize=mdssprep.one_meg*200.,minsize=mdssprep.one_meg*100.)
    # pytest.set_trace()
    t.archive(dryrun=False)
    # setup_module()
    t = mdssprep.Directory('test/test_dir',compress=None,maxarchivesize=mdssprep.one_meg*200.,minsize=mdssprep.one_meg*100.)
    # t.archive(dryrun=False)

def test_verify():

    path = 'test/test_dir/archive_8c70741daa87_001.tar'
    assert(verify(path))

    with tarfile.open(path, mode='a', format=tarfile.PAX_FORMAT) as archive:
        extra = list(archive.members)[0]
        extra.name = 'bogus'
        extra.size = 20
        extra.pax_headers = {'md5': 'bogus'}
        with open("/dev/random", 'rb') as rando:
            archive.addfile(extra, rando)

    assert(not verify(path))
