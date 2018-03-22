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

# External
from yamanifest.manifest import Manifest
from copy import deepcopy
from pwd import getpwnam, getpwuid
from grp import getgrgid
from os import stat
from datetime import date

fast_hashes = ['nchash','binhash']
full_hashes = ['md5']

class PrepManifest(Manifest):
    """
    A manifest object sub-classed from yamanifest object with some specific
    additions and enhancements
    """

    def __init__(self, path, hashes=None, **kwargs):
        super(PrepManifest, self).__init__(path, hashes, **kwargs)

    def check_fast(self, reproduce=False, **args):
        """
        Check hash value for all filepaths using a fast hash function and fall back to slower
        full hash functions if fast hashes fail to agree
        """
        hashvals = {}
        if not self.check_file(filepaths=self.data.keys(),hashvals=hashvals,hashfn=fast_hashes,shortcircuit=True,**args):
            # Run a fast check, if we have failures, deal with them here
            for filepath in hashvals:
                print("Check failed for {} {}".format(filepath,hashvals[filepath]))
                tmphash = {}
                if self.check_file(filepaths=filepath,hashfn=full_hashes,hashvals=tmphash,shortcircuit=False,**args):
                    # File is still ok, so replace fast hashes
                    print("Full hashes ({}) checked ok".format(full_hashes))
                    print("Updating fast hashes for {} in {}".format(filepath,self.path))
                    self.add_fast(filepath,force=True)
                else:
                    # File has changed, update hashes unless reproducing run
                    if not reproduce:
                        print("Updating entry for {} in {}".format(filepath,self.path))
                        self.add_fast(filepath,force=True)
                        self.add(filepath,hashfn=full_hashes,force=True)
                    else:
                        sys.stderr.write("Run cannot reproduce: manifest {} is not correct\n".format(self.path))
                        for fn in full_hashes:
                            sys.stderr.write("Hash {}: manifest: {} file: {}\n".format(fn,self.data[filepath]['hashes'][fn],tmphash[fn]))
                        sys.exit(1)

            # Write updates to version on disk
            self.dump()
            

    def add_fast(self, filepath, hashfn=fast_hashes, force=False):
        """
        Bespoke function to add filepaths but set shortcircuit to True, which means
        only the first calculatable hash will be stored. In this way only one "fast"
        hashing function need be called for each filepath
        """
        self.add(filepath, hashfn, force, shortcircuit=True)

    def add(self, filepaths=None, hashfn=None, force=False, shortcircuit=False, fullpath=None, archive=None):
        """
        Add hash value for filepath given a hashing function (hashfn).
        If no filepaths defined, default to all current filepaths, and in
        this way can add a hash to all existing filepaths.
        If there is already a hash value only overwrite if force=True,
        otherwise raise exception.
        """

        if filepaths is not None:
            if not hasattr(filepaths,'__iter__'):
                filepaths = [filepaths,]
            filepaths = [ str(f) for f in filepaths ] 

        # Call the add method for the class 
        super(PrepManifest, self).add(filepaths=filepaths, hashfn=hashfn, force=force, shortcircuit=shortcircuit, fullpath=fullpath)
        # self.add(filepaths=filepaths, hashfn=hashfn, force=force, shortcircuit=shortcircuit, fullpath=fullpath)

        # Add some metadata
        for filepath in self:
            inf = stat(filepath)
            self.data[filepath]["info"] = {
                "size":inf.st_size,
                "mtime":inf.st_mtime,
                "mtime_long":date.fromtimestamp(inf.st_mtime).strftime("%c"),
                "username":getpwuid(inf.st_uid).pw_name,
                "group":getgrgid(inf.st_gid).gr_name,
            }

        if archive is not None:
            self.data[filepath]["archive"] = archive
