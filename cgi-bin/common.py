#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
  Common functions for cgi-bin

  Copyright 2013-2017 RIKEN

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
'''

__author__ = 'Masatomo Hashimoto <m.hashimoto@riken.jp>'

from pymongo import MongoClient, ASCENDING, DESCENDING
import os
import sys
import json
import simplejson

#

BASE_DIR = '/var/www/outline/treeview'
BASE_URL = '/outline/treeview'

MONGO_PORT = 27017

DEFAULT_USER = 'anonymous'

OUTLINE_DIR_NAME = 'outline'
TARGET_DIR_NAME  = 'target'
TOPIC_DIR_NAME   = 'topic'

DESC_DIR_NAME = 'descriptions'
README_LINKS_DIR_NAME = 'readme_links'

IDX_RANGE_CACHE_NAME = 'idx_range.json'

OUTLINE_DIR = os.path.join(BASE_DIR, OUTLINE_DIR_NAME)
TOPIC_DIR   = os.path.join(BASE_DIR, TOPIC_DIR_NAME)
TARGET_DIR  = os.path.join(BASE_DIR, TARGET_DIR_NAME)

DESC_DIR = os.path.join(BASE_DIR, DESC_DIR_NAME)
README_LINKS_DIR = os.path.join(BASE_DIR, README_LINKS_DIR_NAME)


###

EXPAND_TARGET_LOOPS   = 'expand_target_loops'
EXPAND_RELEVANT_LOOPS = 'expand_relevant_loops'
EXPAND_ALL            = 'expand_all'
COLLAPSE_ALL          = 'collapse_all'

BAR_FMT = '''
<table class="noframe">
<tr>%(prefix)s
<td class="noframe" style="vertical-align:middle">
<div class="bar" style="width:%(width)dpx;">
<div class="barValue" style="width:%(percd)d%%;"></div>
</div>
</td>
<td class="noframe" style="vertical-align:middle;">%(percf)3.2f%%</td>
<td class="noframe" style="vertical-align:middle;">(%(nfinished)d/%(ntargets)d)</td>
</tr>
</table>
'''.replace('\n', '')

NO_BAR_FMT = '''
<table class="noframe"><tr>%s<td class="noframe">N/A</td></tr></table>
'''.replace('\n', '')

TIME_FMT = '<span class="datetime">%s</span>'

NID_SEP = '_'


class NodeManager(object):
    def __init__(self):
        self._node_tbl = {} # nid -> index
        self._node_list = []
        self._node_count = 0
        self._parent_tbl = {} # nid -> node
        self._orig_nid_tbl = {} # nid -> nid list
        self._offset = 1

    def __len__(self):
        return len(self._node_list)

    def set_offset(self, ofs):
        self._offset = ofs

    def reg(self, node):
        self._node_list.append(node)
        nid = node['id']
        self._node_tbl[nid] = self._node_count
        self._node_count += 1
        for c in node['children']:
            self._parent_tbl[c['id']] = node

        orig_nid = nid.split(NID_SEP)[-1]
        if orig_nid != nid:
            try:
                self._orig_nid_tbl[orig_nid].append(nid)
            except KeyError:
                self._orig_nid_tbl[orig_nid] = [nid]

    def get_nid_list(self, nid):
        l = []
        try:
            l = self._orig_nid_tbl[nid]
        except KeyError:
            pass
        return l

    def get(self, nid):
        i = self._node_tbl[nid]
        node = self._node_list[i]
        return node

    def geti(self, idx):
        node = None
        try:
            node = self._node_list[int(idx) - self._offset]
        except:
            pass
        return node

    def iter_subtree(self, node, f):
        ri = node['idx']
        lmi = node['lmi']
        for i in range(lmi-self._offset, ri+1-self._offset):
            try:
                nd = self._node_list[i]
                f(nd)
            except:
                pass

    def iter_parents(self, node, f, itself=False):

        if itself:
            f(node)

        nid = node['id']

        while True:
            parent = self._parent_tbl.get(nid, None)
            if parent:
                f(parent)
                nid = parent['id']
            else:
                break

def get_proj_path(proj):
    return os.path.join(OUTLINE_DIR, proj)

def get_ver_path(proj, ver):
    return os.path.join(OUTLINE_DIR, proj, 'v', ver)

def get_path_list(ver_path):
    path_list = []
    try:
        with open(os.path.join(ver_path, 'path_list.json'), 'r') as plf:
            path_list = simplejson.load(plf)
    except Exception, e:
        pass
    return path_list

def get_fid_list(ver_path):
    fid_list = []
    try:
        with open(os.path.join(ver_path, 'fid_list.json'), 'r') as flf:
            fid_list = simplejson.load(flf)
    except Exception, e:
        pass
    return fid_list

def get_proj_index(proj_path):
    pi_tbl = {}
    try:
        with open(os.path.join(proj_path, 'index.json'), 'r') as pif:
            pi_tbl = simplejson.load(pif)
    except Exception, e:
        pass
    return pi_tbl

def get_ver_index(ver_path):
    vi_tbl = {}
    try:
        with open(os.path.join(ver_path, 'index.json'), 'r') as vif:
            vi_tbl = simplejson.load(vif)
    except Exception, e:
        pass
    return vi_tbl

def get_idx_range_tbl(proj, ver):
    dpath = get_ver_path(proj, ver)
    cache_path = os.path.join(dpath, IDX_RANGE_CACHE_NAME)

    tbl = {} # fid -> (leftmost_idx, idx)

    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            tbl = simplejson.load(f)
    else:
        try:
            for (d, dns, fns) in os.walk(dpath):
                for fn in fns:
                    if fn not in ('index.json', 'fid_list.json', 'path_list.json'):
                        with open(os.path.join(d, fn), 'r') as f:
                            try:
                                d = simplejson.load(f)

                                leftmost_idx = d.get('lmi', None)
                                idx = d.get('idx', None)

                                if leftmost_idx and idx:
                                    fid = d.get('fid', None)
                                    tbl[fid] = (leftmost_idx, idx)
                            except:
                                pass

            with open(cache_path, 'w') as jsonf:
                jsonf.write(json.dumps(tbl))

        except:
            pass

    return tbl


def compute_state(user, proj, ver):
    data = {}
    leftmost_tbl = {} # idx -> leftmost_idx
    node_stat_tbl = {} # idx -> {'judgment','checked','opened','relevant',..}

    try:
        cli = MongoClient('localhost', MONGO_PORT)
        db = cli.loop_survey
        col = db.log

        records = col.find(
            {'$and':[
                {'user':user,'proj':proj,'ver':ver},
                {'$or':[ {'comment':{'$exists':True}},
                         {'judgment':{'$exists':True}},
                         {'estimation_scheme':{'$exists':True}},
                         {'checked':{'$exists':True}},
                         {'opened':{'$exists':True}},
                         {EXPAND_TARGET_LOOPS:True},
                         {EXPAND_RELEVANT_LOOPS:True},
                         {EXPAND_ALL:True},
                         {COLLAPSE_ALL:True},
                     ]}
            ]}
        ).sort('time', ASCENDING)

        def clear_opened(filt=None, key=None, clear_root=False):
            for (idx, stat) in node_stat_tbl.iteritems():
                cond = True
                if filt:
                    (st, ed) = filt
                    if clear_root:
                        cond = st <= idx <= ed
                    else:
                        cond = st <= idx < ed
                
                if cond:
                    if stat.has_key('opened'):
                        b = True
                        if key:
                            b = stat.get(key, False)
                        if b:
                            del stat['opened']

                    if key == 'relevant':
                        snames = [EXPAND_RELEVANT_LOOPS]
                    elif key == 'target':
                        snames = [EXPAND_TARGET_LOOPS]
                    else:
                        snames = [EXPAND_RELEVANT_LOOPS,EXPAND_TARGET_LOOPS,EXPAND_ALL]

                    for sname in snames:
                        if stat.has_key(sname):
                            del stat[sname]

        def clear_key(key, filt):
            for (idx, stat) in node_stat_tbl.iteritems():
                cond = True
                if filt:
                    (st, ed) = filt
                    cond = st <= idx < ed

                if cond:
                    if stat.has_key(key):
                        del stat[key]


        for record in records:
            idx          = record.get('idx', None)
            leftmost_idx = record.get('lmi', None)

            if idx and leftmost_idx:
                if not leftmost_tbl.has_key(idx):
                    leftmost_tbl[idx] = leftmost_idx

                try:
                    stat = node_stat_tbl[idx]
                except KeyError:
                    stat = {}
                    node_stat_tbl[idx] = stat

                def check_bool(key, filt=None):
                    if record.get(key, False):
                        if record[key]:
                            stat[key] = True
                        else:
                            if stat.has_key(key):
                                del stat[key]
                    else:
                        if record.has_key(key):
                            if filt:
                                clear_key(key, filt)
                            if stat.has_key(key):
                                del stat[key]


                if record.get('comment', None) != None:
                    stat['comment'] = record['comment']

                if record.get('judgment', None):
                    stat['judgment'] = record['judgment']

                if record.get('estimation_scheme', None):
                    stat['estimation_scheme'] = record['estimation_scheme']


                filt = (leftmost_idx, idx)

                check_bool('checked', filt=filt)
                check_bool('opened')
                check_bool('relevant')
                check_bool('target')

                check_bool(EXPAND_TARGET_LOOPS)
                check_bool(EXPAND_RELEVANT_LOOPS)
                check_bool(EXPAND_ALL)
                check_bool(COLLAPSE_ALL)

                if stat.get(EXPAND_ALL, False):
                    clear_opened(filt=filt)

                if stat.get(EXPAND_RELEVANT_LOOPS, False):
                    clear_opened(filt=filt, key='relevant')

                if stat.get(EXPAND_TARGET_LOOPS, False):
                    clear_opened(filt=filt, key='target')

                if stat.get(COLLAPSE_ALL, False):
                    clear_opened(filt=filt, clear_root=True)
                    del stat[COLLAPSE_ALL]


        # clean up
        to_be_deleted = []
        for (idx, stat) in node_stat_tbl.iteritems():
            if len(stat) == 0:
                to_be_deleted.append(idx)

        for idx in to_be_deleted:
            del node_stat_tbl[idx]

        data['node_stat'] = node_stat_tbl

    except Exception, e:
        data['failure'] = str(e)


    return data

def get_targets(TARGET_DIR, proj, ver):
    targets = set()
    if proj and ver:
        try:
            with open(os.path.join(TARGET_DIR, proj, ver+'.json'), 'r') as f:
                targets = json.load(f)
        except:
            pass
    else:
        if os.path.exists(TARGET_DIR) and os.path.isdir(TARGET_DIR):
            for proj in os.listdir(TARGET_DIR):
                proj_path = os.path.join(TARGET_DIR, proj)

                if not os.path.isdir(proj_path):
                    continue

                for fn in os.listdir(proj_path):
                    if fn.endswith('.json') and not fn.startswith('roots-'):
                        ver = fn[:-(len('.json'))]
                        try:
                            with open(os.path.join(proj_path, fn), 'r') as f:
                                t = json.load(f)
                            for nid in t:
                                targets.add('%s:%s:%s' % (proj, ver, nid))
                        except:
                            pass

    return targets

def get_progress(TARGET_DIR, user, proj=None, ver=None, nolabel=False):
    progress = '???'
    try:
        cli = MongoClient('localhost', MONGO_PORT)
        col = cli.loop_survey.log

        query = {
            'user':user,
            'target':True,
            'judgment':{'$exists':True},
            'nid':{'$exists':True},
        }

        if proj and ver:
            query['proj'] = proj
            query['ver'] = ver

        records = col.find(query).sort('time', ASCENDING)

        targets = get_targets(TARGET_DIR, proj, ver)

        nfinished = 0

        jtbl = {}

        for record in records:
            nid = record['nid']
            judgment = record['judgment']

            if proj and ver:
                key = nid
            else:
                key = '%s:%s:%s' % (record['proj'], record['ver'], nid)

            if key in targets:
                jtbl[key] = judgment

        for (k, j) in jtbl.iteritems():
            if j != 'NotYet':
                nfinished += 1

        ntargets = len(targets)

        prefix = ''
        width = 100

        if nolabel:
            width = 320

        elif not proj or not ver:
            prefix = '<span style="font-weight:bold;">Overall Progress: </span>'
            prefix = '<td class="noframe">%s</td>' % prefix
            width = 320

        if ntargets > 0:
            progress = BAR_FMT % {
                'prefix'    : prefix,
                'width'     : width,
                'percd'     : nfinished*100/ntargets,
                'percf'     : float(nfinished*100)/float(ntargets),
                'nfinished' : nfinished,
                'ntargets'  : ntargets,
            }
        else:
            progress = NO_BAR_FMT % prefix

    except Exception, e:
        #raise
        pass

    return progress

def get_last_judged(users):
    tbl = {}
    try:
        cli = MongoClient('localhost', MONGO_PORT)
        col = cli.loop_survey.log

        for user in users:
            query = {
                'user':user,
                'proj':{'$exists':True},
                'ver':{'$exists':True},
                'nid':{'$exists':True},
                'judgment':{'$exists':True},
            }
            records = col.find(query).sort('time', DESCENDING).limit(1)

            for record in records:
                time = TIME_FMT % record['time']
                tbl[user] = time
                break

    except Exception, e:
        pass

    return tbl


if __name__ == '__main__':
    print('')
