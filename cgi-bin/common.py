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

NID_RANGE_CACHE_NAME = 'nid_range.json'

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


def nid_to_int(nid):
    return int(nid)

def get_nid_range_tbl(OUTLINE_DIR, proj, ver):
    dpath = os.path.join(OUTLINE_DIR, proj, 'v', ver)
    cache_path = os.path.join(dpath, NID_RANGE_CACHE_NAME)

    tbl = {} # fid -> (leftmost_i, i)

    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            tbl = json.load(f)
    else:
        try:
            for fn in os.listdir(dpath):
                if fn != 'index.json':
                    with open(os.path.join(dpath, fn), 'r') as f:

                        d = json.load(f)

                        leftmost_id = d.get('leftmost_id', None)
                        id = d.get('id', None)

                        if leftmost_id and id:
                            leftmost_i = int(leftmost_id)
                            i = int(id)

                            fid = d.get('fid', None)

                            tbl[fid] = (leftmost_i, i)

            with open(cache_path, 'w') as jsonf:
                json.dump(tbl, jsonf)

        except:
            pass

    return tbl


def compute_state(user, proj, ver):
    data = {}
    leftmost_tbl = {} # nid -> leftmost_nid
    node_stat_tbl = {} # nid -> {'judgment','checked','opened','relevant',..}

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
            for (nid, stat) in node_stat_tbl.iteritems():
                cond = True
                if filt:
                    (st, ed) = filt
                    if clear_root:
                        cond = nid_to_int(st) <= nid_to_int(nid) <= nid_to_int(ed)
                    else:
                        cond = nid_to_int(st) <= nid_to_int(nid) < nid_to_int(ed)
                
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
            for (nid, stat) in node_stat_tbl.iteritems():
                cond = True
                if filt:
                    (st, ed) = filt
                    cond = nid_to_int(st) <= nid_to_int(nid) < nid_to_int(ed)

                if cond:
                    if stat.has_key(key):
                        del stat[key]


        for record in records:
            nid          = record.get('nid', None)
            leftmost_nid = record.get('leftmost_nid', None)

            if nid and leftmost_nid:
                if not leftmost_tbl.has_key(nid):
                    leftmost_tbl[nid] = leftmost_nid

                try:
                    stat = node_stat_tbl[nid]
                except KeyError:
                    stat = {}
                    node_stat_tbl[nid] = stat

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


                filt = (leftmost_nid, nid)

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
        for (nid, stat) in node_stat_tbl.iteritems():
            if len(stat) == 0:
                to_be_deleted.append(nid)

        for nid in to_be_deleted:
            del node_stat_tbl[nid]

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
        raise

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
    print
