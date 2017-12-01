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
from math import log

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

policy = { "compress" : 'gz', "minsize" : 50.*one_meg, "maxarchivesize" : 5.*one_tb, "uncompressible" : ["is_netCDF",] }

strings = [*string.ascii_letters,*string.digits]

def pretty_size(n,pow=0,b=1024,u='B',pre=['']+[p for p in'KMGTPEZY']):
    pow,n=min(int(log(max(n*b**pow,1),b)),len(pre)-1),n*b**pow
    return "%%.%if %%s%%s"%abs(pow%(-pow-1))%(n/b**float(pow),pre[pow],u)

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

    md5string = "{}  {}\n".format(md5sum.hexdigest(),path.name)
    md5info.size = len(md5string)

    archive.addfile(tarinfo=md5info, fileobj=io.BytesIO(md5string.encode('ascii')))

def verify(filename,files,delete):
    """Verify files in archive are the same as on disk
    """
    # Verify files have been archived correctly, then delete originals
    with tarfile.open(name=filename,mode='r:*') as archive:
        for f in files:
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
        self.totalfiles = 0
        self.untarsize = 0
        self.tottarsize = 0
        self.tarsize = 0
        self.narchive = 0
        self.prepped = False
        self.mode = 'w'
        self.verbose = True
        if self.compress is not None:
            self.mode = self.mode+':'+self.compress
                
    def archive(self, dryrun=False):
        self.gatherfiles(dryrun)
        self.report()

    def report(self):
        report_txt="""
Settings        :: minsize: {} maxarchivesize: {}
Number of files :: orig: {} final: {}
Size of files   :: orig: {} final: {}
Average size    :: orig: {} final: {}
        """
        print(report_txt.format(pretty_size(self.minsize), pretty_size(self.maxarchivesize),
            self.totalfiles, self.totalfiles - len(self.tarfiles) + self.narchive,
            pretty_size(self.untarsize+self.tottarsize), pretty_size(self.untarsize+self.tarsize),
            pretty_size((self.untarsize+self.tottarsize)/self.totalfiles),
            pretty_size((self.untarsize+self.tarsize)/(self.totalfiles-len(self.tarfiles)+self.narchive))))

    def gatherfiles(self,dryrun):
        """Archive all files in the directory that meet the size and type criteria
        """
        tarfiles = []
        notarfiles = []
        totsize = 0
        for child in self.path.iterdir():
            if child.is_dir():
                # Do something with directory
                self.subdirs.append(child)
            if child.is_file():
                size = child.stat().st_size
                self.totalfiles += 1
                if size < self.minsize:
                    # print(child,size)
                    tarfiles.append(child)
                    totsize += size
                    self.tottarsize += size
                    if totsize > self.maxarchivesize:
                        self.tar(tarfiles,dryrun)
                        tarfiles = []
                        totsize = 0
                else:
                    notarfiles.append(child)
                    self.untarsize += size

        self.tar(tarfiles,dryrun)
        self.tar(notarfiles,dryrun,store=False)

    def hashpath(self):
        """Make a hash of the path to this directory. Used to uniquely identify
           the archive tar file
        """
        return blake2b(bytes(str(self.path),encoding='ascii'),digest_size=6).hexdigest()

    def tar(self, files, dryrun, store=True):
        """Create archive using tar, delete files after archiving
        """
        if len(files) == 0: return
        self.narchive += 1
        filename = self.path / Path('archive_{}_{:03d}.tar.gz'.format(self.hashpath(),self.narchive))
        if not dryrun:
            try:
                if self.verbose: print("Creating archive {}".format(filename))
                with tarfile.open(name=filename,mode=self.mode,format=tarfile.PAX_FORMAT) as archive:
                    for f in files:
                        if store: archive.add(name=f,arcname=str(f.name))
                        addmd5(archive,f)
            finally:
                if store:
                    # Verify files have been archived correctly, then delete originals
                    verify(filename,files,delete=True)
                    self.tarsize += filename.stat().st_size
                    self.tarfiles.extend(files)
        else:
            if store:
                # The reported size will be too large in the dry-run case (assuming compression
                # of the archive), but this reports a best-case lower bound on average file size
                self.tarsize += self.tottarsize
                self.tarfiles.extend(files)


    
def is_netCDF(ncfile):
    """ Test to see if ncfile is a valid netCDF file
    """
    try:
        tmp = nc.Dataset(ncfile)
        tmp.close()
        return True
    except RuntimeError:
        return False
