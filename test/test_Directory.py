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

sys.path.insert(1, os.path.join(sys.path[0], '..'))

import mdssprep 

verbose = True

def test_make_directory_class():
    t = mdssprep.Directory('.')

    print(t.path, t.minsize, t.maxsize)

    # for f in t.iterdir():
    #     if f.is_file():
    #         print(f,f.stat().st_size)
