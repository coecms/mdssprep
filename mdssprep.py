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
import pwd
import sys
import time
import netCDF4 as nc
import argparse
from warnings import warn
from pathlib import Path
import string
import random
from hashlib import blake2b, md5
import tarfile

from zlib import crc32
import io

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

BLOCK_SIZE = 1024

BUFSIZE = 8*1024

policy = { "compress" : 'gz', "minsize" : 20.*one_meg, "maxsize" : 5.*one_tb, "uncompressible" : ["is_netCDF",] }

strings = [*string.ascii_letters,*string.digits]

def md5path(path):
    """Return the md5 hash instance of a path instance
    """
    m = md5()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(BLOCK_SIZE), b''):
            m.update(chunk)
    return m

def addmd5(archive, path):
    """Add the md5 hash of the path object to an archive
    """
    md5sum = md5path(path)
    md5info = tarfile.TarInfo(name=path.name+'.md5')
 
    # Set some meta data for the md5 hash information
    md5info.mtime = time.time()
    md5info.type = tarfile.REGTYPE
    md5info.mode = 0o644
    md5info.uid = os.getuid()
    md5info.uname = pwd.getpwuid( os.getuid() ).pw_name
    # Inherit group from file
    md5info.gid = path.stat().st_gid
    md5info.gname = path.group()
    md5info.size = md5sum.digest_size

    archive.addfile(tarinfo=md5info, fileobj=io.BytesIO(md5sum.digest()))

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
        self.mode = 'w'
        if self.compress is not None:
            self.mode = self.mode+':'+self.compress
                
    def archive(self):
        self.gatherfiles()
        self.tar()

    def gatherfiles(self):
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

    def hashpath(self):
        """Make a hash of the path to this directory. Used to uniquely identify
           the archive tar file
        """
        return blake2b(bytes(str(self.path),encoding='ascii'),digest_size=6).hexdigest()

    def tar(self):
        """Create archive using tar, delete files after archiving
        """

        filename = self.path / Path('archive_' + self.hashpath() + '.tar.gz')

        try:
            with tarfile.open(name=filename,mode=self.mode,format=tarfile.PAX_FORMAT) as archive:
                for f in self.tarfiles:
                    archive.add(name=f,arcname=str(f.name))
                    addmd5(archive,f)
        finally:
            # Verify files have been archived correctly, then delete originals
            self.verify(filename,delete=True)

    def verify(self,filename,delete):
        """Verify files in archive are the same as on disk
        """
        
        # Verify files have been archived correctly, then delete originals
        with tarfile.open(name=filename,mode='r:*') as archive:
            for f in self.tarfiles:
              try:
                  with archive.extractfile(f.name) as target, f.open("rb") as source:
                      while True:
                          b1 = target.read(BUFSIZE)
                          b2 = source.read(BUFSIZE)
                          if b1 != b2:
                              raise
                          if not b1:
                              break
              finally:
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

    # parser.add_argument("-l","--limited", help="Change unlimited dimension to fixed size (default is to not squash unlimited)", action='store_true')
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

                
