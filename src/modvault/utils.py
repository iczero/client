#-------------------------------------------------------------------------------
# Copyright (c) 2012 Gael Honorez.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#-------------------------------------------------------------------------------

import os
import sys
import urllib2
import re
import shutil

from PyQt4 import QtCore, QtGui

from util import strtodate, datetostr, now, PREFSFILENAME
import util
import logging
from vault import luaparser
import FreeImagePy as FIPY

import cStringIO
import zipfile

logger = logging.getLogger("faf.modvault")
logger.setLevel(logging.DEBUG)

MODFOLDER = os.path.join(util.PERSONAL_DIR, "My Games", "Gas Powered Games", "Supreme Commander Forged Alliance", "Mods")
MODVAULT_DOWNLOAD_ROOT = "http://www.faforever.com/faf/vault/"

MODVAULT_COUNTER_ROOT = "http://www.faforever.com/faf/vault/mods/inc_downloads.php"

installedMods = [] # This is a global list that should be kept intact. So it should be cleared using installedMods[:] = []

class ModInfo(object):
    def __init__(self, **kwargs):
        self.name = "Not filled in"
        self.version = 0
        self.localfolder = ""
        self.__dict__.update(kwargs)

    def setFolder(self, localfolder):
        self.localfolder = localfolder
        self.absfolder = os.path.join(MODFOLDER, localfolder)
        self.mod_info = os.path.join(self.absfolder, "mod_info.lua")

    def update(self):
        self.setFolder(self.localfolder)
        if isinstance(self.version, int):
            self.totalname = "%s v%d" % (self.name, self.version)
        elif isinstance(self.version, float):
            s = str(self.version).rstrip("0")
            self.totalname = "%s v%s" % (self.name, s)
        else:
            raise TypeError, "version is not an int or float"

    def to_dict(self):
        out = {}
        for k,v in self.__dict__.items():
            print k,v
            if isinstance(v, (unicode, str, int, float)) and not k[0] == '_':
                out[k] = v
        return out

    def __str__(self):
        return '%s in "%s"' % (self.totalname, self.folder)

def getAllModFolders(): #returns a list of names of installed mods
        mods = []
        if os.path.isdir(MODFOLDER):
            mods = os.listdir(MODFOLDER)
        return mods
    
def getInstalledMods():
    installedMods[:] = []
    for f in getAllModFolders():
        m = getModInfoFromFolder(f)
        if m:
            installedMods.append(m)
    logger.debug("getting installed mods. Count: %d" % len(installedMods))
    return installedMods
        
def modToFilename(mod):
    return mod.absfolder

def isModFolderValid(folder):
    return os.path.exists(os.path.join(folder,"mod_info.lua"))

def iconPathToFull(path):
    """
    Converts a path supplied in the icon field of mod_info with an absolute path to that file.
    So "/mods/modname/data/icons/icon.dds" becomes
    "C:\Users\user\Documents\My Games\Gas Powered Games\Supreme Commander Forged Alliance\Mods\modname\data\icons\icon.dds"
    """
    if not (path.startswith("/mods") or path.startswith("mods")):
        logger.info("Something went wrong parsing the path %s" % path)
        return ""
    return os.path.join(MODFOLDER, os.path.normpath(path[5+int(path[0]=="/"):])) #yay for dirty hacks

def fullPathToIcon(path):
    p = os.path.normpath(os.path.abspath(path))
    return p[len(MODFOLDER)-5:].replace('\\','/')

def parseModInfo(folder):
    if not isModFolderValid(folder):
        return None
    modinfofile = luaparser.luaParser(os.path.join(folder,"mod_info.lua"))
    modinfo = modinfofile.parse({"name":"name","uid":"uid","version":"version","author":"author",
                                 "description":"description","ui_only":"ui_only",
                                 "icon":"icon"},
                                {"version":"1","ui_only":"false","description":"","icon":"","author":""})
    modinfo["ui_only"] = (modinfo["ui_only"] == 'true')
    if not "uid" in modinfo:
        return None
    modinfo["uid"] = modinfo["uid"].lower()
    try:
        modinfo["version"] = int(modinfo["version"])
    except:
        try:
            modinfo["version"] = float(modinfo["version"])
        except:
            logger.warn("Couldn't convert version to int in %s: %s" % (folder, modinfo["version"]))
    return (modinfofile, modinfo)

modCache = {}
def getModInfoFromFolder(modfolder): # modfolder must be local to MODFOLDER
    if modfolder in modCache:
        return modCache[modfolder]

    r = parseModInfo(os.path.join(MODFOLDER,modfolder))
    if r == None:
        logger.debug("mod_info.lua not found in %s folder" % modfolder)
        return None
    f, info = r
    if f.error:
        logger.debug("Error in parsing %s/mod_info.lua" % modfolder)
        return None
    m = ModInfo(**info)
    m.setFolder(modfolder)
    m.update()
    modCache[modfolder] = m
    return m

def getActiveMods(uimods=None): # returns a list of ModInfo's containing information of the mods
    """uimods:
        None - return all active mods
        True - only return active UI Mods
        False - only return active non-UI Mods
    """
    l = luaparser.luaParser(PREFSFILENAME)
    modlist = l.parse({"active_mods":"active_mods"},{"active_mods":{}})["active_mods"]
    if l.error:
        logger.info("Error in reading the game.prefs file")
        return []
    uids = [uid.lower() for uid,b in modlist.items() if b == 'true']
    #logger.debug("Active mods detected: %s" % str(uids))
    
    allmods = []
    for m in installedMods:
        if ((uimods == True and m.ui_only) or (uimods == False and not m.ui_only) or uimods == None):
            allmods.append(m)
    active_mods = [m for m in allmods if m.uid.lower() in uids]
    #logger.debug("Allmods uids: %s\n\nActive mods uids: %s\n" % (", ".join([mod.uid for mod in allmods]), ", ".join([mod.uid for mod in allmods])))
    return active_mods

def setActiveMods(mods, keepuimods=True): #uimods works the same as in getActiveMods
    """
    keepuimods:
        None: Replace all active mods with 'mods'
        True: Keep the UI mods already activated activated
        False: Keep only the non-UI mods that were activated activated
        So set it True if you want to set gameplay mods, and False if you want to set UI mods.
    """
    if keepuimods != None:
        keepTheseMods = getActiveMods(keepuimods) # returns the active UI mods if True, the active non-ui mods if False
    else:
        keepTheseMods = []
    allmods = keepTheseMods + mods
    s = "active_mods = {\n"
    for mod in allmods:
        s += "['%s'] = true,\n" % str(mod.uid)
    s += "}"

    try:
        f = open(PREFSFILENAME, 'r')
        data = f.read()
    except:
        logger.info("Couldn't read the game.prefs file")
        return False
    else:
        f.close()

    if re.search("active_mods\s*=\s*{.*?}", data, re.S):
        data = re.sub("active_mods\s*=\s*{.*?}",s,data,1,re.S)
    else:
        data += "\n" + s

    try:
        f = open(PREFSFILENAME, 'w')
        f.write(data)
    except:
        logger.info("Cound't write to the game.prefs file")
        return False
    else:
        f.close()

    return True

def updateModInfo(mod, info): #should probably not be used.
    """
    Updates a mod_info.lua file with new data.
    Because those files can be random lua this function can fail if the file is complicated enough
    If every value however is on a seperate line, this should work.
    """
    fname = mod.mod_info
    try:
        f = open(fname, 'r')
        data = f.read()
    except:
        logger.info("Something went wrong reading %s" % fname)
        return False
    else:
        f.close()

    for k,v in info.items():
        if type(v) in (bool,int): val = str(v).lower()
        if type(v) in (unicode, str): val = '"' + v.replace('"', '\\"') + '"'
        if re.search(r'^\s*'+k, data , re.M):
            data = re.sub(r'^\s*' + k + r'\s*=.*$',"%s = %s" % (k,val), data, 1, re.M)
        else:
            if data[-1] != '\n': data += '\n'
            data += "%s = %s" % (k, val)
    try:
        f = open(fname, 'w')
        f.write(data)
    except:
        logger.info("Something went wrong writing to %s" % fname)
        return False
    else:
        f.close()
        
    return True


def generateThumbnail(sourcename, destname):
    """Given a dds file, generates a png file (or whatever the extension of dest is"""
    logger.debug("Creating png thumnail for %s to %s" % (sourcename, destname))
    f = FIPY.Image(sourcename)
    f.setSize((100,100))
    f.save(destname)
    if os.path.isfile(destname):
        return True
    else:
        return False

def downloadMod(item): #most of this function is stolen from fa.maps.downloadMap
    if isinstance(item,basestring):
        link = MODVAULT_DOWNLOAD_ROOT + urllib2.quote("mods/" + item + ".zip")
    else:
        link = item.link
    logger.debug("Getting mod from: " + link)

    link = urllib2.quote(link, "http://")
    progress = QtGui.QProgressDialog()
    progress.setCancelButtonText("Cancel")
    progress.setWindowFlags(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    
    try:
        req = urllib2.Request(link, headers={'User-Agent' : "FAF Client"})         
        zipwebfile  = urllib2.urlopen(req)

        meta = zipwebfile.info()
        file_size = int(meta.getheaders("Content-Length")[0])
        print file_size
        print meta
        progress.setMinimum(0)
        progress.setMaximum(file_size)
        progress.setModal(1)
        progress.setWindowTitle("Downloading Mod")
        progress.setLabelText(link)
    
        progress.show()

        #Download the file as a series of 8 KiB chunks, then uncompress it.
        output = cStringIO.StringIO()
        file_size_dl = 0
        block_sz = 8192       

        while progress.isVisible():
            read_buffer = zipwebfile.read(block_sz)
            if not read_buffer:
                break
            file_size_dl += len(read_buffer)
            output.write(read_buffer)
            progress.setValue(file_size_dl)
    
        progress.close()
        
        if file_size_dl == file_size:
            zfile = zipfile.ZipFile(output)
            print MODFOLDER
            zfile.extractall(MODFOLDER)
            logger.debug("Successfully downloaded and extracted mod from: " + link)
        else:    
            logger.warn("Mod download cancelled for: " + link)
            return False

    except:
        logger.warn("Mod download or extraction failed for: " + link)        
        if sys.exc_type is urllib2.HTTPError:
            logger.warning("ModVault download failed with HTTPError, mod probably not in vault (or broken).")
            QtGui.QMessageBox.information(None, "Mod not downloadable", "<b>This mod was not found in the vault (or is broken).</b><br/>You need to get it from somewhere else in order to use it." )
        else:                
            logger.error("Download Exception", exc_info=sys.exc_info())
            QtGui.QMessageBox.information(None, "Mod installation failed", "<b>This mod could not be installed (please report this map or bug).</b>")
        return False

    return True
    

def removeMod(mod):
    if mod not in installedMods:
        return
    shutil.rmtree(mod.absfolder)
    if mod.localfolder in modCache:
        del modCache[mod.localfolder]
    installedMods.remove(mod)
    
