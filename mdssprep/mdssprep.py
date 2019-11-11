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
from itertools import compress

from zlib import crc32
import io

# Local import
from mdssprep.manifest import PrepManifest

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

policy = { "compress" : 'gz', "minfilesize" : 50.*one_meg, "maxarchivesize" : 10.*one_gig, "uncompressible" : ["is_netCDF",] }

strings = [*string.ascii_letters,*string.digits]

def set_policy(**kwargs):
    global policy
    policy.update(**kwargs)

def pretty_size(n,pow=0,b=1024,u='B',pre=['']+[p for p in'KMGTPEZY']):
    pow,n=min(int(log(max(n*b**pow,1),b)),len(pre)-1),n*b**pow
    return "%%.%if %%s%%s"%abs(pow%(-pow-1))%(n/b**float(pow),pre[pow],u)

def is_netCDF(ncfile):
    """ Test to see if ncfile is a valid netCDF file
    """
    try:
        tmp = nc.Dataset(ncfile)
        tmp.close()
        return True
    except RuntimeError:
        return False
def md5stream(handle):
    """Return the md5 hash instance of a path instance
    """
    m = md5()
    for chunk in iter(lambda: handle.read(BLOCK_SIZE), b''):
        m.update(chunk)
    return m

def md5path(path):
    """Return the md5 hash instance of a path instance
    """
    with path.open('rb') as f:
        m = md5stream(f)
    return m

def oldaddmd5(archive, path):
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

def addmeta(info):
    """
    Add the md5 hash of the path object to an tarfile TarInfo object
    and ensure path is local to the directory by replacing with just
    the pathlib name attribute
    """
    info.pax_headers = {'md5': md5path(Path(info.name)).hexdigest()}
    info.name = Path(info.name).name
    return info

def verify(filename):
    """
    Verify files in archive match their internal md5 checksums
    Return True if all files match, False otherwise
    """
    # Verify files have been archived correctly, then delete originals
    with tarfile.open(name=filename, mode='r') as archive:
        for f in archive.getmembers():
            with archive.extractfile(f) as target:
                md5sum = md5stream(target).hexdigest()
                if md5sum != f.pax_headers['md5']:
                    # Short-circuit and return on first hash mismatch
                    print(f.name, md5sum, f.pax_headers['md5'])
                    return False
    return True

class Directory(object):
    """A directory on the filesystem

    Attributes:
        path: a Path object for the directory
        minfilesize: size (in bytes) below which a file should be archived
        prepped: logical indicating if the directory has been prepared for archiving
        tarfiles: list of files to add to the archive
    """

    def __init__(self, path, **kwargs):
        """Return an mdssDirectory object"""
        self.path = Path(path)
        self.parent = self.path.parent
        kwargs = {**policy, **kwargs}
        self.include = []
        self.exclude = []
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

        # Recursively descend through subdirectories
        for path in self.subdirs:
            d = Directory(path)
            d.archive(dryrun)

    def report(self):
        report_txt="""
Settings        :: minfilesize: {} maxarchivesize: {}
Number of files :: orig: {} final: {}
Size of files   :: orig: {} final: {}
Average size    :: orig: {} final: {}
        """
        print(report_txt.format(pretty_size(self.minfilesize), pretty_size(self.maxarchivesize),
            self.totalfiles, self.totalfiles - len(self.tarfiles) + self.narchive,
            pretty_size(self.untarsize+self.tottarsize), pretty_size(self.untarsize+self.tarsize),
            pretty_size((self.untarsize+self.tottarsize)/self.totalfiles),
            pretty_size((self.untarsize+self.tarsize)/(self.totalfiles-len(self.tarfiles)+self.narchive))))

    def gatherfiles(self,dryrun):
        """Archive all files in the directory that meet the size and type criteria
        """
        tarfiles = []
        store = []
        totsize = 0
        for child in self.path.iterdir():
            if child.is_dir():
                # Do something with directory
                self.subdirs.append(child)
            if child.is_file():
                size = child.stat().st_size
                self.totalfiles += 1
                tarfiles.append(child)
                exclude = False
                include = False
                for pattern in self.include:
                    if child.match(pattern):
                        if self.verbose: print("{} matched include filter {}\n".format(child.name,pattern))
                        include = True
                        break
                for pattern in self.exclude:
                    if child.match(pattern):
                        if self.verbose: print("{} matched exlude filter {}\n".format(child.name,pattern))
                        exclude = True
                        break
                if (size < self.minfilesize and not exclude) or include:
                    totsize += size
                    self.tottarsize += size
                    self.tarsize += size
                    store.append(True)
                    if totsize > self.maxarchivesize:
                        self.tar(tarfiles,store,dryrun)
                        tarfiles = []
                        totsize = 0
                        store = []
                else:
                    self.untarsize += size
                    store.append(False)

        self.tar(tarfiles,store,dryrun)

    def hashpath(self):
        """Make a hash of the path to this directory. Used to uniquely identify
           the archive tar file
        """
        return blake2b(bytes(str(self.path),encoding='ascii'),digest_size=6).hexdigest()

    def tar(self, files, storemask, dryrun):
        """Create archive using tar, delete files after archiving
        """
        if len(files) == 0: return
        self.narchive += 1
        hashval = self.hashpath()
        filename = 'archive_{}_{:03d}.tar'.format(hashval,self.narchive)
        if self.compress:
            filename = ":".join([filename, self.compress])
        filename = self.path / Path(filename)
        if not dryrun:
            try:
                if self.verbose: print("Creating archive {}".format(filename))
                with tarfile.open(
                                  name=filename,
                                  mode=self.mode,
                                  format=tarfile.PAX_FORMAT) as archive:
                    for path in compress(files,storemask):
                        archive.add(name=path,
                                    filter=addmeta,
                                    recursive=False)
            finally:
                # Verify files have been archived correctly, then delete originals
                if verify(filename):
                    for path in compress(files,storemask):
                        os.unlink(path)
                else:
                    print("WARNING! Files not compressed correctly: "+files)
        else:
            # The reported size will be too large in the dry-run case (assuming compression
            # of the archive), but this reports a worst-case lower bound on average file size
            self.tarsize += self.tottarsize

        self.tarfiles.extend(list(compress(files,storemask)))