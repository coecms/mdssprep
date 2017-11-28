#!/usr/bin/env python3

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

import subprocess
import os
import sys
import netCDF4 as nc
import argparse
from warnings import warn
from pathlib import Path
import string
import random
from hashlib import blake2b

# A couple of hard-wired executable paths that might need changing

# Need to use system time command explicitly, otherwise get crippled bash version
timecmd='/usr/bin/time'
nccopy='nccopy'
nc2nc='nc2nc'
cdocmd='cdo'

result_list=[]

one_meg = 1048576.
one_gig = 1073741824.
one_tb = 1099511627776.

policy = { "minsize" : 20.*one_meg, "maxsize" : 5.*one_tb, "uncompressible" : ["is_netCDF",] }

strings = [*string.ascii_letters,*string.digits]

class Directory(object):
    """A directory on the filesystem

    Attributes:
        path: a Path object for the directory
        minsize: size (in bytes) below which a file should be archived
        prepped: logical indicating if the directory has been prepared for archiving
        tarfiles: list of files to add to the archive
    """

    def __init__(self, path, **kwargs):
        """Return an mdssDirectory object"""
        self.path = Path(path)
        kwargs = {**policy, **kwargs}
        for key, val in kwargs.items():
            setattr(self, key, val)
        self.tarfiles = []
        self.subdirs = []
        self.prepped = False
                
    def archive(self):
        """Archive all files in the directory that meet the size and type criteria
        """
        for child in self.path.iterdir():
            if child.is_dir():
                # Do something with directory
                self.subdirs.append(child)
            if child.is_file():
                if child.stat().st_size < self.minsize:
                    print(child,child.stat().st_size)
                    self.tarfiles.append(child)
        self.tar()

    def hash(self):
        """Make a hash of the path to this directory. Used to uniquely identify
           the archive tar file
        """
        return blake2b(bytes(str(self.path),encoding='ascii'),digest_size=6).hexdigest()

    def tar(self):
        """Create archive using tar, delete files after archiving
        """

        tarfile = self.path / Path('archive_' + self.hash() + '.tar')
        tarcmd = ['tar', '-C', str(self.path), '--verify', '-c', '-f', str(tarfile)]

        # The archive is local, so strip off all directory information
        tarcmd.extend([ str(f.name) for f in self.tarfiles])

        print(" ".join(tarcmd))
        proc = subprocess.run(tarcmd)
        if proc.returncode != 0:
            print("Something went wrong with following command:\n{}".format(proc.args))
        else:
            # Remove the files we have archived. Can't use the --delete-files option
            # of tar, as it breaks verification
            for f in self.tarfiles:
                f.unlink()
            

    
def is_netCDF(ncfile):
    """ Test to see if ncfile is a valid netCDF file
    """
    try:
        tmp = nc.Dataset(ncfile)
        tmp.close()
        return True
    except RuntimeError:
        return False

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Iterate over directories making the suitable for archiving them to tape storage")

    parser.add_argument("-d","--dlevel", help="Set deflate level. Valid values 0-9 (default=5)", type=int, default=5, choices=range(0,10), metavar='{1-9}')
    # parser.add_argument("-l","--limited", help="Change unlimited dimension to fixed size (default is to not squash unlimited)", action='store_true')
    parser.add_argument("-t","--tmpdir", help="Specify temporary directory to save compressed files", default='tmp.nc_compress')
    parser.add_argument("-v","--verbose", help="Verbose output", action='store_true')
    parser.add_argument("-r","--recursive", help="Recursively descend directories and run mdssprep on them (default False)", action='store_true')
    parser.add_argument("-p","--paranoid", help="Paranoid check : run nco ndiff on the resulting file ensure no data has been altered", action='store_true')
    parser.add_argument("-pa","--parallel", help="Prep directories in parallel", action='store_true')
    parser.add_argument("-np","--numproc", help="Specify the number of processes to use in parallel operation", type=int, default=1)
    parser.add_argument("inputs", help="directories (-r must be specified to recursively descend directories)", nargs='+')
    args = parser.parse_args()
    
    verbose=args.verbose

    # We won't make users specify parallel if they've specified a number of processors
    if args.numproc: args.parallel = True

    if args.parallel:
        if args.numproc is not None:
            numproc = args.numproc
        else:
            numproc = mp.cpu_count()

    filedict = defaultdict(list)

    # Loop over all the inputs from the command line. These can be either file globs
    # or directory names. In either case we'll group them by directory
    for ncinput in args.inputs:
        if not os.path.exists(ncinput):
            print ("Input does not exist: {} .. skipping".format(ncinput))
            continue
        if os.path.isdir(ncinput):
            # Check that we haven't been here already
            if ncinput in filedict: continue
            # os.walk will return the entire directory structure
            for root, dirs, files in os.walk(ncinput):
                # Ignore emtpy directories, and our own temp directory, in case we
                # re-run on same tree
                if len(files) == 0: continue
                if root.endswith(args.tmpdir): continue
                # Check that we haven't been here already
                if root in filedict: continue
                # Only descend into subdirs if we've set the recursive flag
                if (root != ncinput and not args.recursive):
                    print("Skipping subdirectories of {0} :: --recursive option not specified".format(ncinput))
                    break
                else:
                    # Compress all the files in this directory
                    compress_files(root,files,args.tmpdir,args.overwrite,args.maxcompress,args.dlevel,not args.noshuffle,args.force,args.clean,verbose,args.buffersize,args.nccopy,args.paranoid,numproc,args.timing)
                    # Note we've traversed this directory but set directory to an empty list
                    filedict[root] = []
        else:
            (root,file) = os.path.split(ncinput)
            if (root == ''): root = "./"
            filedict[root].append(file)

    # Files that were specified directly on the command line are compressed by directory.
    # We only create a temporary directory once, and can then clean up after ourselves.
    # Also makes it easier to run some checks to ensure compression is ok, as all the files
    # are named the same, just in a separate temporary sub directory.
    for directory in filedict:
        if len(filedict[directory]) == 0: continue
        compress_files(directory,filedict[directory],args.tmpdir,args.overwrite,args.maxcompress,args.dlevel,not args.noshuffle,args.force,args.clean,verbose,args.buffersize,args.nccopy,args.paranoid,numproc,args.timing)

                
