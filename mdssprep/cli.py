#!/usr/bin/env python3

"""
Copyright 2018 ARC Centre of Excellence for Climate Systems Science

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

from __future__ import print_function, absolute_import

import os, sys
import argparse
import mdssprep

def parse_args(args):
    """
    Parse arguments given as list (args)
    """
    parser = argparse.ArgumentParser(description="Run mdssprep on one or more directories")

    parser.add_argument("-n","--dryrun", help="Dry run, no files archived", action='store_true')
    parser.add_argument("-v","--verbose", help="Verbose output", action='store_true')
    parser.add_argument("dirs", help="Directories to prep for mdss", nargs='+')

    return parser.parse_args(args)

def main(args):
    """
    Main routine. Takes return value from parse.parse_args as input
    """

    print(vars(args))
    for dir in args.dirs:
        prepdir = mdssprep.Directory(dir, **vars(args))
        prepdir.archive(dryrun=args.dryrun)

def main_parse_args(args):
    """
    Call main with list of arguments. Callable from tests
    """
    # Must return so that check command return value is passed back to calling routine
    # otherwise py.test will fail
    return main(parse_args(args))

def main_argv():
    """
    Call main and pass command line arguments. This is required for setup.py entry_points
    """
    main_parse_args(sys.argv[1:])

if __name__ == "__main__":

    main_argv()
